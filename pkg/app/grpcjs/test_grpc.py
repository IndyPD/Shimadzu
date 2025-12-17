import grpc_servicer

grpc_master = grpc_servicer.GRPCGlobalVariableTaskServicer()
grpc_master.run_server()