# 빈 Ubuntu에 서버 환경 구축
## anaconda 설치

1. anaconda download
    
    sudo wget [https://repo.anaconda.com/archive/Anaconda3-2021.11-Linux-x86_64.sh](https://repo.anaconda.com/archive/Anaconda3-2021.11-Linux-x86_64.sh)
    
2. download 파일 실행
    
    bash Anaconda3-2021.11-Linux-x86_64.sh
    
3. conda 실행되는 지 확인
    - conda list 명령어 실행
        - list 뜨면 설치 성공!
        - 안 뜨면 아래의 명령어를 실행 → 모든 계정(root X)에서 anaconda 사용 가능하도록 경로 수정
            - echo 'export PATH="/home/이름/anaconda3/bin:$PATH"' >> ~/.bashr
            - source ~/.bashrc

## cuda 설치

### 이전의 cuda 삭제

- sudo apt-get purge nvidia*
- sudo apt-get autoremove
- sudo apt-get autoclean
- sudo rm -rf /usr/local/cuda*

### cuda 파일 다운로드

1. [https://developer.nvidia.com/cuda-toolkit-archive](https://developer.nvidia.com/cuda-toolkit-archive) 접속
2. 원하는 버전의 cuda 선택
3. 자신의 환경과 맞게 설정
    ![image](https://user-images.githubusercontent.com/62591011/204449616-33d8d63d-beed-4e78-8789-dda7a962918f.png)

    
4. 아래 명령어 부분 복사 후 입력
    ![image](https://user-images.githubusercontent.com/62591011/204449652-59aab9c2-bd50-47a4-8141-44ad10c592d3.png)    
    - wget [https://developer.download.nvidia.com/compute/cuda/11.1.1/local_installers/cuda-repo-ubuntu1804-11-1-local_11.1.1-455.32.00-1_amd64.deb](https://developer.download.nvidia.com/compute/cuda/11.1.1/local_installers/cuda-repo-ubuntu1804-11-1-local_11.1.1-455.32.00-1_amd64.deb)
    - sudo dpkg -i cuda-repo-ubuntu1804-11-1-local_11.1.1-455.32.00-1_amd64.deb
    - (생략해도 되는 듯?) sudo apt-key add /var/cuda-repo-ubuntu1804-11-1-local/7fa2af80.pub
    - sudo apt-get update
    - sudo apt-get -y install cuda

### cuda 설치 확인

- nvcc —version
- nvidia-smi

## jupyter config 수정

1. 파이썬 설치 
    - sudo apt-get install python3-pip
2. jupyter config 생성
    - jupyter notebook --generate-config
3. jupyter config 수정 (외부 접속 가능하게 하기 위해)
    - vi ~/.jupyter/jupyter_notebook_config.py
    - 아래 내용 추가
        
        c = get_config()
        c.NotebookApp.ip = '0.0.0.0'
        c.NotebookApp.open_browser = False
        c.NotebookApp.port = 8888 # 사용할 port 번호
        
4. jupyter 실행 
    
    jupyter notebook --port=8888 --no-browser
    
5. 비밀번호 생성
    1. 위의 명령어 입력 후 나온 토큰 복사해서 넣기
    2. 비밀번호 설정(ex. 1234)
    

## git 설치

1. git download
    - sudo apt install git-all
2. ssh key 생성
    1. 폴더 들어가기
        
        cd ~/.ssh
        
    2. 존재하는 key 확인 
        
        ls
        
    3. 새로운 key 생성
        
        ssh-keygen -t ed25519 -C "메일주소"
        
        위의 명령어 입력 후 enter 3번
        
    4. 생성된 key 등록  
        
        cat id_ed25519.pub 입력  
        
        key 값 복사해서 github에 ssh key 등록  
        
    5. ssh config 수정  
        
        vi ~/.ssh/config 입력 후 아래 내용 추가
        
        Host [github.com](http://github.com/)
        IdentityFile ~/.ssh/id_ed25519
        User git
