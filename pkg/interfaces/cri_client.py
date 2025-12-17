
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.append(impl_path)

from common_msgs_pb2 import *
from cri_msgs_pb2 import *
from cri_pb2_grpc import *
from cri_pb2 import *

while impl_path in sys.path:
    sys.path.remove(impl_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
from google.protobuf import json_format
import grpc
import common as Common
import managers as Managers

import socket
try:
    import fcntl
except:
    print("Failed to import fcntl - CRI disabled")
import struct
import requests

ETHERNET_LIST = ["eth1", "enp2s0"]

class CRIClient:
    def __init__(self, ip_addr, port=Common.Config().CRI_SOCKET_PORT):
        try:
            cri_channel = grpc.insecure_channel("{}:{}".format(ip_addr, port))
            cri_stub = CRIStub(cri_channel)
            self.__cri_stub = Common.Utils.StubWithTimeout(stub=cri_stub, timeout=Common.Limits.GRPCTimeOut)
        except Exception as e:
            print(f"failed to CRI Servicer, {e}")

    def get_mac_addresses(self, interface):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            mac = fcntl.ioctl(sock.fileno(), 0x8927, struct.pack('256s', interface[:15].encode('utf-8')))
            return ':'.join(['%02x' % b for b in mac[18:24]])
        except:
            return ""

    # @Common.Utils.exception_handler
    # def set_activate(self, on: bool):
    #     return self.__cri_stub.SetActivate(State(enable = on))
    #
    # @Common.Utils.exception_handler
    # def is_activate(self):
    #     return self.__cri_stub.IsActivate(Empty()).enable

    @Common.Utils.exception_handler
    def login(self, email:str, token:str):
        return self.__cri_stub.LoginSFD(SFDAccount(email=email, token=token))

    @Common.Utils.exception_handler
    def is_login(self):
        return self.__cri_stub.IsSFDLogin(Empty()).enable

    @Common.Utils.exception_handler
    def logout(self):
        return self.__cri_stub.LogoutSFD(Empty())
    @Common.Utils.exception_handler
    def get_account(self):
        res = self.__cri_stub.GetSFDLoginInfo(Empty())
        return {"email":res.email, "token":res.token}

    @Common.Utils.exception_handler
    def save_account(self, email:str, token:str):
        return self.__cri_stub.SaveSFDLoginInfo(SFDAccount(email=email, token=token))

    @Common.Utils.exception_handler
    def load_account(self):
        res = self.__cri_stub.LoadSFDLoginInfo(Empty())
        return {"email":res.email, "token":res.token}

    @Common.Utils.exception_handler
    def select_target(self, pn:str, fn:str, rn:str, iso:bool):
        return self.__cri_stub.SelectSFDTarget(SFDTarget(pn=pn, fn=fn, rn=rn, iso=iso))

    @Common.Utils.exception_handler
    def release_target(self):
        return self.__cri_stub.ReleaseSFDTarget(Empty()).enable

    @Common.Utils.exception_handler
    def is_target_valid(self):
        return self.__cri_stub.IsSFDTargetValid(Empty()).enable

    @Common.Utils.exception_handler
    def get_target(self):
        res = self.__cri_stub.GetSFDTarget(Empty())
        return {"pn":res.pn, "fn":res.fn, "rn":res.rn, "iso":res.iso}

    @Common.Utils.exception_handler
    def active_cri_vel(self, on:bool):
        return self.__cri_stub.ActiveCRIVel(State(enable = on))

    @Common.Utils.exception_handler
    def get_proj_list(self):
        # return self.__cri_stub.GetSFDProjList(Empty()).list
        proj = ""
        if self.is_login():
            acs = self.__cri_stub.GetSFDLoginInfo(Empty())
            email = acs.email
            token = acs.token
            # print("email:", email, ", token:", token)

            url = "https://api.safetics.io/openapi/v1/project-robot-list-n" \
                  + "?email=" + email

            headers = {
                "Authorization": f"Bearer {token}"
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                proj = str(response.json())
        return proj

    @Common.Utils.exception_handler
    def get_cri(self):
        res = self.__cri_stub.GetCRI(Empty())
        return {"time":res.time, "cri":res.cri, "velRatio":res.velRatio}

    @Common.Utils.exception_handler
    def generate_token(self, email):
        # res = self.__cri_stub.GenerateSFDToken(Empty())

        token = ""
        mac = ""
        for interface in ETHERNET_LIST:
            mac += self.get_mac_addresses(interface)
        print("Generate Safetics Token by email:", email, ", mac_addr:", mac)

        url = 'https://api.safetics.io/openapi/v1/rt-analysis-token-gen'
        data = {
            "email": email,
            "macaddress": mac
        }

        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                token = response.json()["api_token"]
                self.__cri_stub.SaveSFDLoginInfo(SFDAccount(email=email, token=token))
            else:
                print("Failed to Generate Token-", response.status_code)
        except Exception as err:
            token = ""
            print("Failed to Generate Token")

        return token

    @Common.Utils.exception_handler
    def save_auto_set(self, login:bool, pn:str, fn:str, rn:str, iso:bool):
        return self.__cri_stub.SaveSFDAutoSet(SFDAutoSet(login=login, pn=pn,
                                                        fn=fn, rn=rn, iso=iso))

    @Common.Utils.exception_handler
    def load_auto_set(self):
        res = self.__cri_stub.LoadSFDAutoSet(Empty())
        return {"login":res.login , "pn": res.pn, "fn": res.fn, "rn":res.rn, "iso": res.iso}

############################
# Main
############################
if __name__ == "__main__":
    ip = '192.168.0.91'
    cri = CRIClient(ip)
    time.sleep(1)
