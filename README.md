# LargeScale 대규모 데이터 학습
## 분산 학습 및 HALP(High Accuracy Low Precision)를 적용한 대규모 데이터 학습
- 인공지능융합학과 김가연, 심유라, 컴퓨터공학과 박도영

## Senario
- 딥러닝 모델을 학습하는 과정에서, 대규모 데이터셋을 학습시킬 경우 많은 연산 시간이 소요
  - 학습 시간을 단축하는 기술인 **분산 학습** 적용
- 'Flickr8k' 데이터를 이용한 이미지 캡셔닝
![image](https://user-images.githubusercontent.com/45381907/200161064-b25c16cd-7b6a-471e-b4e6-c406a3e848dc.png)
  - 출처 : https://medium.com/@raman.shinde15/image-captioning-with-flickr8k-dataset-bleu-4bcba0b52926
- 모델
  - image feature extract model : **ResNet**
  - captioning model : **Transformer**
  
  
## communication cost 줄이기 위한 quantization 기법 **HALP** : High-Accuracy Low-Precision SGD
