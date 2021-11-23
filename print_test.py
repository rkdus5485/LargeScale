def print_test():
    epoch_time=[1,2,3]
    with open('/home/rkdus5485/download/notebooks/ImageCaptioning.pytorch/time_list/base_train_time.txt', 'w') as output_file:
            for i in epoch_time:
                output_file.write(str(i) + '\n')
                
print_test()
