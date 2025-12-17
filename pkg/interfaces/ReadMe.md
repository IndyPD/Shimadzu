# Interface usages

## Vive TeleOp

### How To Run
- 기존과 같이 HTC Vive를 별도 PC에 셋업 (참고: 아래 Vive Installation Instructions)
- Vive PC에 *common*, *interfaces* , *managers* 폴더와 *ViveTeleDeviceTest.py*, *__init__.py* 파일을 복사
- *teleop_server_vive.py* 파일에서 아래 부분에 연결된 장치 이름과 트리거에 사용되는 버튼 타입을 입력
```python
DEVICE_NAME = "tracker_1"
TRIGGE_NAME = "menu_button"
```
- *teleop_server_vive.py*를 실행 혹은 *ViveTeleDeviceTest.ipynb* 파일에서 server.start()까지 실행
- IndyDeploy.json에서 TeleoperationTask를 활성화하고 인디 프레임워크를 다시 실행
- Conty로 접속해 설정 > 프로그램환경 > 텔레오퍼레이션 탭 접속
- 교시 장치는 VIVE 선택, Vive PC의 IP를 입력하고 PORT 번호 20500 입력 후 연결
  - 연결하면 아래에 교시 장치로부터 들어오는 좌표값이 표시됨
- <캘리브레이션 시작> 하면 10cm 큐브를 그리며 캘리브레이션 수행 (방향 맞추는 과정)
  - 이때 엔드툴에 Vive 교시 장치를 부착해두어도 되고, 교시 장치를 직접 들고 로봇의 동작을 따라해도 됨
- <녹화 시작> 한 뒤, 트리거 버튼을 누르면 원격 조종이 시작됨. 트리거를 누른 동안의 동작이 기록
- <모션 실행> 누르면 녹화된 동작이 실행됨
- 모션 이름을 입력하고 <업데이트> 버튼을 누르면 해당 모션이 저장됨

### Vive Installation Instructions
출처: https://github.com/rnb-disinfection/rnb-track/blob/main/ReadMe.md

0. Install Steam, as well as Python and OpenVR dependencies (https://store.steampowered.com/about/)
* (FOR CUDA USER) Steam needs 32bit graphic drivers. If 64bit driver is already installed, it will fail at updates.
  * Add repository for 32bit drivers
  ```bash
  sudo apt-add-repository 'deb http://kr.archive.ubuntu.com/ubuntu/ bionic-updates main restricted'  \
  && sudo apt-add-repository 'deb http://security.ubuntu.com/ubuntu bionic-security main restricted'
  ```
  * install 32 bit graphic drivers and **REBOOT**. this will remove many packages related to cuda and nvidia. check the exact driver versions before they are removed.
  ```bash
  sudo apt-get install libnvidia-gl-460:i386 libvulkan1:i386
  ```
  * start steam - required packages will be installed in a new terminal.
  
1. Make Steam account & Log in.

2. Install SteamVR  on Steam

3. Make a Symbolic Link from libudev.so.0 to libudev.so.1 for SteamVR to use

`sudo ln -s /lib/x86_64-linux-gnu/libudev.so.1 /lib/x86_64-linux-gnu/libudev.so.0`

4. Install pyopenvr

```bash
sudo pip3 install -U pip openvr \
&& pip3 install serial pyserial
```

5. Disable the headset requirement with your preferred text editor  
  * Edit the file ``` ~/.steam/steam/steamapps/common/SteamVR/resources/settings/default.vrsettings ``` 
    1. Search for the “requireHmd” key under “steamvr”, set the value of this key to false.
    2. Search for the “forcedDriver” key under “steamvr”, set the value of this key to null.
    3. Search for the “activateMultipleDrivers” key under “steamvr”, set the value of this key to true.  
  * Edit the file ``` ~/.steam/steam/steamapps/common/SteamVR/drivers/null/resources/settings/default.vrsettings```
    1. Search for the "enable" key under "driver_null", set the value of this key to true.
        
6. Set directory environment variable
```bash
export RNB_TRACK_DIR=$HOME/Projects/rnb-track/ \
&& echo 'export RNB_TRACK_DIR=$HOME/Projects/rnb-track/' >> ~/.bashrc
```
7. (FOR CUDA USER) After all all process done, remove the 32 bit driver and re-install the exact version of 64bit graphic drivers that were installed before. below is un example.
  ```bash
  sudo apt remove --purge libnvidia-gl-460:i386 \
  && sudo apt-get install --no-install-recommends nvidia-driver-460=460.106.00-0ubuntu1 \
    libxnvctrl0=460.106.00-0ubuntu1 \
    nvidia-modprobe=460.106.00-0ubuntu1 \
    nvidia-settings=460.106.00-0ubuntu1 \
  && sudo apt-get install cuda-drivers=460.106.00-1 \
  && sudo apt-get install --no-install-recommends cuda-11-2=11.2.1-1
  ```
  * Now, even if steam does not open due to some error, you can use vr by opening vrmonitor

#### Vive Coordinates
![vive_coordinates](./images/vive_coordinates.jpg)

#### Basic Test with triad_openvr

1. Start SteamVR from the Steam Library

2. Turn on the tracker with its button, and make sure that its wireless USB dongle is plugged in to your computer. If the tracker shows up in the SteamVR overlay skip to step 4.

3. Sync the tracker. Hold the button on the tracker until the light blinks. On the SteamVR overlay click the "SteamVR" dropdown menu. Click Devices->Pair Controller. The Tracker should then pair with the computer, and a green outline of the tracker should appear on the SteamVR overlay. If this doesn't work try unplugging the wireless USB dongle, plugging it back in, and restarting SteamVR. 

4. Ensure the Lighthouse base stations are turned on, facing each other, and have green lights showing on them. Place the tracker in view of the Base Stations. The SteamVR overlay should now show two green square Base Stations and a solid green Tracker hexagon. The tracker is now working.

5. Start the tracker_test.py python script to view the x y z roll pitch yaw output from the tracker.

```
cd triad_openvr/
python3 ./tracker_test.py
```

6. If everything went well you should now see the data coming from the Tracker. Use tracker_test.py as a sample program to work from to integrate into your project.

#### Command Line

To start SteamVR from the commandline you can run (as one command):

`LD_LIBRARY_PATH=~/.steam/bin32/ ~/.steam/bin32/steam-runtime/run.sh ~/.steam/steam/steamapps/common/SteamVR/bin/vrstartup.sh`

This will start the server in another process, so you're free to keyboard interrupt (Ctrl+C) the terminal once the server starts. 

To kill the SteamVR process:

`sudo killall -9 vrmonitor`

#### Links

https://github.com/TriadSemi/triad_openvr.git