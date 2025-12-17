import os

current_directory = os.getcwd()
print(current_directory)

# Path of proto file
build_protobuf_file = "EtherCATCommgRPCServer.proto"
proto_file_directory = current_directory + "\\grpcjs\\proto"
proto_file_path = current_directory + "\\grpcjs\\proto\\" + build_protobuf_file
output_path = current_directory + "\\grpcjs\\grpc_gen"

# Create output directory if it doesn't exist
if not os.path.exists(output_path):
    os.makedirs(output_path)

# Generate gRPC code command
print("asdfa")
os.system(f"python -m grpc_tools.protoc --proto_path={proto_file_directory} --python_out={output_path} --grpc_python_out={output_path} {proto_file_path}")
print("asdfa")