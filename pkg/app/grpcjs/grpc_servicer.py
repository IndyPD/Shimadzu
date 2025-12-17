import threading
import grpc
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
from concurrent import futures
import template_pb2_grpc
import template_pb2

GRPC_SERVER_PORT_DEFAULT = 502

class GRPCGlobalVariableTaskServicer(template_pb2_grpc.GRPCGlobalVariableTaskServicer):
    def __init__(self):
        self.running = False
        self.thread = None
        self.val = [0] * 1000
        # id에 따라 문자열을 저장하기 위한 딕셔너리
        self.string_vals = {}

    def SetInt(self, request, context):
        response = template_pb2.Empty()
        self.val[request.idx] = request.val
        return response

    def GetInt(self, request, context):
        '''

        '''
        response = template_pb2.IntVal()
        response.val = self.val[request.val]
        return response

    def SetInts(self, request, context):
        '''
            App --> Server --> Blackboard
        '''

        for i in range(len(request.val)):
            self.val[request.idx+i] = request.val[i]

        response = template_pb2.Empty()
        return response

    def GetInts(self, request, context):

        response = template_pb2.IntVals()
        for i in range(request.val):
            response.val.append(self.val[request.idx+i])
        return response

    # 새로운 SetStringWithId 메서드 구현
    def SetStringWithId(self, request, context):
        self.string_vals[request.id] = request.val
        # print(f"SetStringWithId called: id={request.id}, val={request.val}")
        response = template_pb2.Empty()
        return response

    # 새로운 GetStringWithId 메서드 구현
    def GetStringWithId(self, request, context):
        response = template_pb2.StringWithId()
        response.id = request.id
        # 해당 id의 문자열 값이 없으면 빈 문자열을 반환
        response.val = self.string_vals.get(request.id, "")
        # print(f"GetStringWithId called: id={request.id}, val={response.val}")
        return response

    def SaveGlobalVariables(self, request, context):

        response = template_pb2.Empty()
        return response

    def LoadGlobalVariables(self, request, context):

        response = template_pb2.Empty()
        return response
    
    def run(self, port=GRPC_SERVER_PORT_DEFAULT):
        server_man = grpc.server(futures.ThreadPoolExecutor(max_workers=100))
        template_pb2_grpc.add_GRPCGlobalVariableTaskServicer_to_server(GRPCGlobalVariableTaskServicer(), server_man)
        server_man.add_insecure_port(f'[::]:{port}')
        server_man.start()
        server_man.wait_for_termination()

    def run_server(self, port=GRPC_SERVER_PORT_DEFAULT):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, args=(port,), daemon=True)
            self.thread.start()
            
    def stop_server(self):
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()
