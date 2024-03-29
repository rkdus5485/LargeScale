from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter
from torch.multiprocessing import Process
## 이거 import 해
import captioning.utils.opts as opts
#import captioning.utils.torchhalp.optim.svrg as SVRG
#import captioning.utils.torchhalp.optim.halp as HALP
from captioning.utils.torchhalp.optim import SVRG, HALP
from torch.autograd import Variable
import torch.distributed as dist
import numpy as np
import torch.multiprocessing as mp
import time
import os
from six.moves import cPickle
import traceback
from collections import defaultdict


import captioning.models as models
from captioning.data.dataloader import *
import skimage.io
import captioning.utils.eval_utils as eval_utils
import captioning.utils.misc as utils
from captioning.utils.rewards import init_scorer, get_self_critical_reward
from captioning.modules.loss_wrapper import LossWrapper

def init_processes(rank, wordsize, train, opt):
    """ Initialize the distributed environment. """
    """#도영
    #os.environ['MASTER_ADDR'] = '34.64.214.227'
    #가연
    os.environ['MASTER_ADDR'] = '34.64.150.44'
    #os.environ['MASTER_ADDR'] = '34.64.150.44'
    os.environ['MASTER_PORT'] = '44444'
    os.environ['WORLD_SIZE'] = "3"
    os.environ['RANK'] = '0'
    #os.environ['CUDA_VISIBLE_DEVICES']='0,1,2'"""
    
    os.environ['MASTER_ADDR'] = '192.168.0.34'
    os.environ['MASTER_PORT'] = '20211'
    os.environ['CUDA_VISIBLE_DEVICES']='0,1'
    
    
    #print("before init_process_group")
    
    dist.init_process_group(backend="gloo",rank=rank, world_size=wordsize)
    
    #print("after init_process_group")
    train(opt)
    
def average_gradients(model):
    """ Gradient averaging."""
    size = float(dist.get_world_size())
    #print('average size : ', size)
    for param in model.parameters():
        #group = dist.new_group(ranks=None)
        #print('average 한당 !!!!!!!!!!!')
        #print('데이터 : ',param.grad.data)
        
        #dist.reduce(torch.tensor([1]).to('cuda'),dst=0,op=dist.ReduceOp.SUM)
        dist.reduce(param.grad.data, dst=0, op=dist.ReduceOp.SUM)
        #print('안뇽')
        #dist.all_reduce(param.grad.data, op=dist.ReduceOp.SUM)
        dist.broadcast(param.grad.data, src=0)
        #print('햇당 ~!')
        param.grad.data /= size
        #print('average 했다 !!!!!!')
def add_summary_value(writer, key, value, iteration):
    if writer:
        writer.add_scalar(key, value, iteration)

def train(opt):
    epoch_time = []

    ################################
    # Build dataloader
    ################################
    loader = DataLoader(opt)
    opt.vocab_size = loader.vocab_size
    opt.seq_length = loader.seq_length

    ##########################
    # Initialize infos
    ##########################
    infos = {
        'iter': 0,
        'epoch': 0,
        'loader_state_dict': None,
        'vocab': loader.get_vocab(),
    }
    # Load old infos(if there is) and check if models are compatible
    if opt.start_from is not None and os.path.isfile(os.path.join(opt.start_from, 'infos_'+opt.id+'.pkl')):
        with open(os.path.join(opt.start_from, 'infos_'+opt.id+'.pkl'), 'rb') as f:
            infos = utils.pickle_load(f)
            saved_model_opt = infos['opt']
            need_be_same=["caption_model", "rnn_type", "rnn_size", "num_layers"]
            for checkme in need_be_same:
                assert getattr(saved_model_opt, checkme) == getattr(opt, checkme), "Command line argument and saved model disagree on '%s' " % checkme
    infos['opt'] = opt

    #########################
    # Build logger
    #########################
    # naive dict logger
    histories = defaultdict(dict)
    if opt.start_from is not None and os.path.isfile(os.path.join(opt.start_from, 'histories_'+opt.id+'.pkl')):
        with open(os.path.join(opt.start_from, 'histories_'+opt.id+'.pkl'), 'rb') as f:
            histories.update(utils.pickle_load(f))

    # tensorboard logger
    tb_summary_writer = SummaryWriter(opt.checkpoint_path)

    ##########################
    # Build model
    ##########################
    opt.vocab = loader.get_vocab()
    model = models.setup(opt).cuda()
    del opt.vocab
    # Load pretrained weights:
    if opt.start_from is not None and os.path.isfile(os.path.join(opt.start_from, 'model.pth')):
        model.load_state_dict(torch.load(os.path.join(opt.start_from, 'model.pth')))
    
    # Wrap generation model with loss function(used for training)
    # This allows loss function computed separately on each machine
    lw_model = LossWrapper(model, opt)
    # Wrap with dataparallel
    #dp_model = torch.nn.DataParallel(model)
    #dp_model.vocab = getattr(model, 'vocab', None)  # nasty
    #dp_lw_model = torch.nn.DataParallel(lw_model)
    #dp_lw_model = torch.nn.DataParallel(lw_model, output_device=0)
    ##########################
    #  Build optimizer
    ##########################
    optimizer = HALP(model.parameters(), lr=opt.learning_rate, T=1, data_loader=loader)
    # Load the optimizer
    if opt.start_from is not None and os.path.isfile(os.path.join(opt.start_from,"optimizer.pth")):
        optimizer.load_state_dict(torch.load(os.path.join(opt.start_from, 'optimizer.pth')))

    #########################
    # Get ready to start
    #########################
    iteration = infos['iter']
    epoch = infos['epoch']
    # For back compatibility
    if 'iterators' in infos:
        infos['loader_state_dict'] = {split: {'index_list': infos['split_ix'][split], 'iter_counter': infos['iterators'][split]} for split in ['train', 'val', 'test']}
    loader.load_state_dict(infos['loader_state_dict'])
    if opt.load_best_score == 1:
        best_val_score = infos.get('best_val_score', None)
    if opt.noamopt:
        optimizer._step = iteration
    # flag indicating finish of an epoch
    # Always set to True at the beginning to initialize the lr or etc.
    epoch_done = True
    # Assure in training mode
    lw_model.train()
    #dp_lw_model.train()

    # Start training
    try:
        epoch_list = []
        s = time.time()
        epoch_list.append(s)
        while True:
            epoch_start_time = time.time()
            # Stop if reaching max epochs
            if epoch >= opt.max_epochs and opt.max_epochs != -1:
                break

            if epoch_done:
                
                if not opt.noamopt and not opt.reduce_on_plateau:
                    # Assign the learning rate
                    if epoch > opt.learning_rate_decay_start and opt.learning_rate_decay_start >= 0:
                        frac = (epoch - opt.learning_rate_decay_start) // opt.learning_rate_decay_every
                        decay_factor = opt.learning_rate_decay_rate  ** frac
                        opt.current_lr = opt.learning_rate * decay_factor
                    else:
                        opt.current_lr = opt.learning_rate
                    utils.set_lr(optimizer, opt.current_lr) # set the decayed rate
                # Assign the scheduled sampling prob
                if epoch > opt.scheduled_sampling_start and opt.scheduled_sampling_start >= 0:
                    frac = (epoch - opt.scheduled_sampling_start) // opt.scheduled_sampling_increase_every
                    opt.ss_prob = min(opt.scheduled_sampling_increase_prob  * frac, opt.scheduled_sampling_max_prob)
                    model.ss_prob = opt.ss_prob
                    
                if opt.self_critical_after != -1 and epoch >= opt.self_critical_after:
                    sc_flag = True
                    init_scorer(opt.cached_tokens)
                else:
                    sc_flag = False
                
                # If start structure loss training
                if opt.structure_after != -1 and epoch >= opt.structure_after:
                    struc_flag = True
                    init_scorer(opt.cached_tokens)
                else:
                    struc_flag = False
                if opt.drop_worst_after != -1 and epoch >= opt.drop_worst_after:
                    drop_worst_flag = True
                else:
                    drop_worst_flag = False

                epoch_done = False
                    
            start = time.time()
            if opt.use_warmup and (iteration < opt.noamopt_warmup):
                opt.current_lr = opt.learning_rate * (iteration+1) / opt.noamopt_warmup
                utils.set_lr(optimizer, opt.current_lr)
            # Load data from train split (0)
            data = loader.get_batch('train')
            #print('Read data:', time.time() - start)

            torch.cuda.synchronize()
            start = time.time()

            tmp = [data['fc_feats'], data['att_feats'], data['labels'], data['masks'], data['att_masks']]
            tmp = [_ if _ is None else _.cuda() for _ in tmp]
            fc_feats, att_feats, labels, masks, att_masks = tmp
            gts = data['gts']
            # print(next(iter(loader.loaders['train']))) -> fc_feats,att_feats,att_masks,labels,masks,gts,bounds,infos
            
            ################################################
            # closure
            ################################################
            def closure(fc_feats=fc_feats, att_feats=att_feats, labels=labels, masks=masks, att_masks=att_masks, gts=gts):
                fc_feats = Variable(fc_feats, requires_grad=False)
                att_feats = Variable(att_feats, requires_grad=False)
                labels = Variable(labels, requires_grad=False)
                masks = Variable(masks, requires_grad=False)
                #att_masks = Variable(att_masks, requires_grad=False)
                cuda = torch.cuda.is_available()
                if cuda:
                    fc_feats, att_feats, labels, masks = fc_feats.cuda(), att_feats.cuda(), labels.cuda(), masks.cuda()
                #output = dp_lw_model(fc_feats, att_feats, labels, masks, att_masks, data['gts'], torch.arange(0, len(data['gts'])), 0, 0, 0)
                output = lw_model(fc_feats, att_feats, labels, masks, att_masks, data['gts'], torch.arange(0, len(data['gts'])), 0, 0, 0)
                loss = output['loss'].mean()
                loss.backward()
                return loss
            
            optimizer.zero_grad()
            
            
            '''model_out = dp_lw_model(fc_feats, att_feats, labels, masks, att_masks, data['gts'], torch.arange(0, len(data['gts'])), sc_flag, struc_flag, drop_worst_flag)
            if not drop_worst_flag:
                loss = model_out['loss'].mean()
            else:
                loss = model_out['loss']
                loss = torch.topk(loss, k=int(loss.shape[0] * (1-opt.drop_worst_rate)), largest=False)[0].mean()
            loss.backward()'''
            
            
            if opt.grad_clip_value != 0:
                getattr(torch.nn.utils, 'clip_grad_%s_' %(opt.grad_clip_mode))(model.parameters(), opt.grad_clip_value)
                # print('drop_worst_flag',drop_worst_flag)
            optimizer.step(closure)
            train_loss = closure().item()
            torch.cuda.synchronize()
            end = time.time()
            
            
            """if iteration%300==0:
                if struc_flag:
                    print("iter {} (epoch {}), train_loss = {:.3f}, lm_loss = {:.3f}, struc_loss = {:.3f}, time/batch = {:.3f}" \
                        .format(iteration, epoch, train_loss, model_out['lm_loss'].mean().item(), model_out['struc_loss'].mean().item(), end - start))
                elif not sc_flag:
                    print("iter {} (epoch {}), train_loss = {:.3f}, time/batch = {:.3f}" \
                        .format(iteration, epoch, train_loss, end - start))
                else:
                    print("iter {} (epoch {}), avg_reward = {:.3f}, time/batch = {:.3f}" \
                        .format(iteration, epoch, model_out['reward'].mean(), end - start))"""
            
            
            if struc_flag:
                print("iter {} (epoch {}), train_loss = {:.3f}, lm_loss = {:.3f}, struc_loss = {:.3f}, time/batch = {:.3f}" \
                    .format(iteration, epoch, train_loss, model_out['lm_loss'].mean().item(), model_out['struc_loss'].mean().item(), end - start))
            elif not sc_flag:
                print("iter {} (epoch {}), train_loss = {:.3f}, time/batch = {:.3f}" \
                    .format(iteration, epoch, train_loss, end - start))
            else:
                print("iter {} (epoch {}), avg_reward = {:.3f}, time/batch = {:.3f}" \
                    .format(iteration, epoch, model_out['reward'].mean(), end - start))

            # Update the iteration and epoch
            iteration += 1
            #print('data : ',data)
            if data['bounds']['wrapped']:
                epoch += 1
                epoch_done = True
                e = time.time()
                epoch_list.append(e)
                print('epoch per time(end_time) : ', epoch_list[epoch]-epoch_list[epoch-1]) 
                epoch_time.append(epoch_list[epoch]-epoch_list[epoch-1])

            # Write the training loss summary
            if (iteration % opt.losses_log_every == 0):
                tb_summary_writer.add_scalar('train_loss', train_loss, iteration)
                if opt.noamopt:
                    opt.current_lr = optimizer.rate()
                elif opt.reduce_on_plateau:
                    opt.current_lr = optimizer.current_lr
                tb_summary_writer.add_scalar('learning_rate', opt.current_lr, iteration)
                tb_summary_writer.add_scalar('scheduled_sampling_prob', model.ss_prob, iteration)
                if sc_flag:
                    tb_summary_writer.add_scalar('avg_reward', model_out['reward'].mean(), iteration)
                elif struc_flag:
                    tb_summary_writer.add_scalar('lm_loss', model_out['lm_loss'].mean().item(), iteration)
                    tb_summary_writer.add_scalar('struc_loss', model_out['struc_loss'].mean().item(), iteration)
                    tb_summary_writer.add_scalar('reward', model_out['reward'].mean().item(), iteration)
                    tb_summary_writer.add_scalar('reward_var', model_out['reward'].var(1).mean(), iteration)

                histories['loss_history'][iteration] = train_loss if not sc_flag else model_out['reward'].mean()
                histories['lr_history'][iteration] = opt.current_lr
                histories['ss_prob_history'][iteration] = model.ss_prob
            """epoch_end_time = time.time() - epoch_start_time
            epoch_time.append(epoch_end_time)"""
            
            

            # update infos
            infos['iter'] = iteration
            infos['epoch'] = epoch
            infos['loader_state_dict'] = loader.state_dict()
            
            # make evaluation on validation set, and save model
            if (iteration % opt.save_checkpoint_every == 0 and not opt.save_every_epoch) or \
                (epoch_done and opt.save_every_epoch):
                # eval model
                eval_kwargs = {'split': 'val',
                                'dataset': opt.input_json}
                eval_kwargs.update(vars(opt))
                val_loss, predictions, lang_stats = eval_utils.eval_split(
                    dp_model, lw_model.crit, loader, eval_kwargs)

                if opt.reduce_on_plateau:
                    if 'CIDEr' in lang_stats:
                        optimizer.scheduler_step(-lang_stats['CIDEr'])
                    else:
                        optimizer.scheduler_step(val_loss)
                # Write validation result into summary
                tb_summary_writer.add_scalar('validation loss', val_loss, iteration)
                if lang_stats is not None:
                    for k,v in lang_stats.items():
                        tb_summary_writer.add_scalar(k, v, iteration)
                histories['val_result_history'][iteration] = {'loss': val_loss, 'lang_stats': lang_stats, 'predictions': predictions}

                # Save model if is improving on validation result
                if opt.language_eval == 1:
                    current_score = lang_stats['CIDEr']
                else:
                    current_score = - val_loss

                best_flag = False

                if best_val_score is None or current_score > best_val_score:
                    best_val_score = current_score
                    best_flag = True

                # Dump miscalleous informations
                infos['best_val_score'] = best_val_score

                utils.save_checkpoint(opt, model, infos, optimizer, histories)
                if opt.save_history_ckpt:
                    utils.save_checkpoint(opt, model, infos, optimizer,
                        append=str(epoch) if opt.save_every_epoch else str(iteration))

                if best_flag:
                    utils.save_checkpoint(opt, model, infos, optimizer, append='best')
           
        
        # 여기 경로 고치세유 ~~
        """with open('/home/rkdus5485/BERT/Bigdata/ImageCaptioning.pytorch/time_list/halp_train_time.txt', 'w') as output_file:
            for i in epoch_time:
                output_file.write(str(i) + '\n')"""
        with open(os.path.join(opt.checkpoint_path,'base_train_time.txt'), 'w') as output_file:
            for i in epoch_time:
                output_file.write(str(i) + '\n')

    except (RuntimeError, KeyboardInterrupt):
        print('Save ckpt on exception ...')
        utils.save_checkpoint(opt, model, infos, optimizer)
        print('Save ckpt done.')
        stack_trace = traceback.format_exc()
        print(stack_trace)
        
    


opt = opts.parse_opt()
train(opt)
"""if __name__ == "__main__":
    #size = 1
    #print('시작')
    
    world_size=2
    processes=[]
    size=2
    for rank in range(size):
        if rank==0:
            opt.input_json='data/f8ktalk_1.json'
        else:
            opt.input_json='data/f8ktalk_2.json'
        p = mp.Process(target=init_processes, args=(rank, world_size, train, opt))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()"""
