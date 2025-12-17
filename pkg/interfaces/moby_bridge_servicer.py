from concurrent import futures

import grpc

## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect
import os
import sys
root_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root_path)
impl_path = os.path.join(os.path.dirname(__file__), 'impl')
sys.path.insert(0, impl_path)
impl_old_path = os.path.join(os.path.dirname(__file__), 'impl_old')
sys.path.insert(0, impl_old_path)
cur_path = os.path.join(os.path.dirname(__file__), '.')
sys.path.append(cur_path)

import common_msgs_pb2
import moby_msgs_pb2, moby_pb2_grpc
import ethercat_msgs_pb2, ethercat_pb2_grpc
import MobygRPCServer_pb2, MobygRPCServer_pb2_grpc

while cur_path in sys.path:
    sys.path.remove(cur_path)
while impl_old_path in sys.path:
    sys.path.remove(impl_old_path)
while impl_path in sys.path:
    sys.path.remove(impl_path)
while root_path in sys.path:
    sys.path.remove(root_path)
## relative import can cause error in python grpc. add impl to path to import and remove to prevent side-effect

class GRPCMobyTaskServicer(MobygRPCServer_pb2_grpc.GRPCMobyTaskServicer):
    ecat_channel: grpc.insecure_channel
    moby_channel: grpc.insecure_channel
    ecat_stub: ethercat_pb2_grpc.EtherCATStub
    moby_stub: moby_pb2_grpc.MobyStub

    def __init__(self, ecat_port=20000, moby_port=20006):
        localhost = '127.0.0.1'
        self.ecat_name = f"{localhost}:{ecat_port}"
        self.moby_name = f"{localhost}:{moby_port}"
        self.connect()

    def GetMobyTxData(self, request: MobygRPCServer_pb2.IntVal, context) -> MobygRPCServer_pb2.MotorDriverTx:
        try:
            servo_tx = self.ecat_stub.GetServoTx(ethercat_msgs_pb2.ServoIndex(servoIndex=request.val))
            return MobygRPCServer_pb2.MotorDriverTx(statusWord=servo_tx.statusWord,
                                                    modeOpDisp=servo_tx.modeOpDisp,
                                                    actualPosition=servo_tx.actualPosition,
                                                    actualVelocity=servo_tx.actualVelocity,
                                                    actualTorque=servo_tx.actualTorque
                                                    )
        except Exception as e:
            self.check_reopen()
            raise e

    def GetDriveSpeed(self, request: MobygRPCServer_pb2.Empty, context) -> MobygRPCServer_pb2.SwerveDoubles:
        try:
            swerve_doubles = self.moby_stub.GetDriveSpeed(common_msgs_pb2.Empty())
            return MobygRPCServer_pb2.SwerveDoubles(fl=swerve_doubles.fl,
                                                    fr=swerve_doubles.fr,
                                                    bl=swerve_doubles.bl,
                                                    br=swerve_doubles.br)
        except Exception as e:
            self.check_reopen()
            raise e

    def DriveWheel(self, request: MobygRPCServer_pb2.SwerveDoubles, context) -> MobygRPCServer_pb2.Empty:
        try:
            self.moby_stub.DriveWheel(
                moby_msgs_pb2.SwerveDoubles(fl=request.fl,
                                            fr=request.fr,
                                            bl=request.bl,
                                            br=request.br))
            return MobygRPCServer_pb2.Empty()
        except Exception as e:
            self.check_reopen()
            raise e

    def GetRotationAngleDeg(self, request: MobygRPCServer_pb2.Empty, context) -> MobygRPCServer_pb2.SwerveDoubles:
        try:
            swerve_doubles = self.moby_stub.GetRotationAngleDeg(common_msgs_pb2.Empty())
            return MobygRPCServer_pb2.SwerveDoubles(fl=swerve_doubles.fl,
                                                    fr=swerve_doubles.fr,
                                                    bl=swerve_doubles.bl,
                                                    br=swerve_doubles.br)
        except Exception as e:
            self.check_reopen()
            raise e

    def SetRotationAngleDeg(self, request: MobygRPCServer_pb2.SwerveDoubles, context) -> MobygRPCServer_pb2.Empty:
        try:
            self.moby_stub.SetRotationAngleDeg(
                moby_msgs_pb2.SwerveDoubles(fl=request.fl,
                                            fr=request.fr,
                                            bl=request.bl,
                                            br=request.br))
            return MobygRPCServer_pb2.Empty()
        except Exception as e:
            self.check_reopen()
            raise e

    def GetMobyState(self, request: MobygRPCServer_pb2.Empty, context) -> MobygRPCServer_pb2.MobyState:
        try:
            moby_state = self.moby_stub.GetMobyState(common_msgs_pb2.Empty())
            isready = moby_state.is_ready
            isenable = moby_state.is_enable
            return MobygRPCServer_pb2.MobyState(isReady=(isready and isenable))
        except Exception as e:
            self.check_reopen()
            raise e

    def check_reopen(self) -> bool:
        try:
            grpc.channel_ready_future(self.ecat_channel).result(timeout=0.5)
            grpc.channel_ready_future(self.moby_channel).result(timeout=0.5)
            return True
        except grpc.FutureTimeoutError:
            print("GRPCGlobalVariableTaskStub Channel Timeout Error - Try Reconnection")
            try:
                self.disconnect()
                self.connect()
            finally:
                return False
        except Exception as e:
            print("GRPCGlobalVariableTaskStub Channel Unexpected Error - Try Reconnection")
            print(e)
            try:
                self.disconnect()
                self.connect()
            finally:
                return False

    def connect(self):
        self.ecat_channel = grpc.insecure_channel(self.ecat_name)
        self.moby_channel = grpc.insecure_channel(self.moby_name)
        self.ecat_stub = ethercat_pb2_grpc.EtherCATStub(self.ecat_channel)
        self.moby_stub = moby_pb2_grpc.MobyStub(self.moby_channel)

    def disconnect(self):
        self.ecat_channel.close()
        self.moby_channel.close()


def serve_moby_bridge(host="[::]", port=50051, ecat_port=20000, moby_port=20006, wait_for_termination=False):
    moby_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10),
                              options=[('grpc.max_send_message_length', 10 * 1024 * 1024),
                                       ('grpc.max_receive_message_length', 10 * 1024 * 1024)]
                              )
    moby_servicer = GRPCMobyTaskServicer(ecat_port=ecat_port, moby_port=moby_port)
    MobygRPCServer_pb2_grpc.add_GRPCMobyTaskServicer_to_server(servicer=moby_servicer, server=moby_server)
    moby_server.add_insecure_port(f'{host}:{port}')
    moby_server.start()
    if wait_for_termination:
        moby_server.wait_for_termination()
    return moby_server, moby_servicer


if __name__ == "__main__":
    serve_moby_bridge(wait_for_termination=True)
