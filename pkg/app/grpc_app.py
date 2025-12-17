from .base import ModbusStyleClientBase, ModbusStyleCommunication
from .grpcjs import grpc_servicer, grpc_client


class GRPCAppCommunication(ModbusStyleCommunication):
    ##
    # @brief start the server here
    def start_server(self):
        self.grpc_master = grpc_servicer.GRPCGlobalVariableTaskServicer()
        self.grpc_master.run_server(port=int(self.server_info["grpc_port"]))

    ##
    # @brief start the server here
    def get_client(self) -> ModbusStyleClientBase:
        return grpc_client.gRPC_Client(self.server_info["address"], int(self.server_info["grpc_port"]))
