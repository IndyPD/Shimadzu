# Shimadzu Project

Shimadzu 로직 및 장치 제어 프로젝트입니다.

## 환경 설정 (Installation)

이 프로젝트는 Anaconda 환경(`NRMK`)과 Python 3.8을 기준으로 작성되었습니다.

### 1. Conda 가상환경 생성 및 활성화

Anaconda Prompt 또는 터미널에서 아래 명령어를 실행하여 가상환경을 생성하고 활성화합니다.

```bash
# 가상환경 생성 (이름: NRMK, Python 버전: 3.8)
conda create -n NRMK python=3.8

# 가상환경 활성화
conda activate NRMK
```

### 2. 라이브러리 설치

프로젝트 실행에 필요한 라이브러리들을 한 번에 설치합니다.

```bash
pip install -r requirements.txt
```

> **참고:** `requirements.txt`에는 다음 라이브러리들이 포함되어 있습니다.
> - pycomm3 (EtherNet/IP 통신)
> - pyserial (시리얼 통신)
> - paho-mqtt (MQTT 통신)
> - grpcio, protobuf (gRPC 통신)
> - requests, numpy
> - PyYAML (설정 파일 처리)
> - semver (버전 관리)
> - psutil (시스템 프로세스 관리)
> - py_trees (Behavior Tree 구현)
> - neuromeka (Indy 로봇 제어)
> - scipy (과학 계산)

## 실행 방법 (Usage)

프로젝트 루트 경로에서 `run.py`를 실행합니다.

```bash
python run.py --project shimadzu_logic
```
