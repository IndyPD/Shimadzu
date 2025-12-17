from .base import ModbusStyleClientBase, ModbusStyleCommunication
from pyModbusTCP.client import ModbusClient as ModbusClientTCP
from pyModbusTCP.server import ModbusServer as ModbusServerTCP
from threading import Thread


class ModbusClient(ModbusStyleClientBase):

    def __init__(self, ip, port=502):
        self._modbus_client = ModbusClientTCP(host=ip, port=port)

    def check_reopen(self) -> bool:
        try:
            if callable(self._modbus_client.is_open):
                is_open = self._modbus_client.is_open()
            else:
                is_open = self._modbus_client.is_open
            if not is_open:
                self._modbus_client.open()
            return is_open
        except Exception as e:
            print("Failed to reopen modbus channel")
            print(e)
            return False

    def set_int(self, idx, val):
        self._modbus_client.write_single_register(idx, val)

    def set_ints(self, idx, val):
        self._modbus_client.write_multiple_registers(idx, val)

    # def get_int(self, idx):
    #     return self._modbus_client.read_holding_registers(idx, 1)[0]
        
    def get_int(self, idx):
        try:
            result = self._modbus_client.read_holding_registers(idx, 1)
            if result is not None and len(result) > 0:
                return result[0]
            else:
                print("No data returned from read_holding_registers")
                return None  # 또는 적절한 오류 처리
        except Exception as e:
            print(f"Error reading holding register at index {idx}: {e}")
            return None  # 또는 적절한 오류 처리


    def get_ints(self, idx, count):
        if count<120:
            return self._modbus_client.read_holding_registers(idx, count)
        else:
            return_data = self._modbus_client.read_holding_registers(idx, 120)
            for i in range(1,int(count/120)+1):
                return_data+=self._modbus_client.read_holding_registers(idx+120*i, 120)
            return return_data


class ModbusAppCommunication(ModbusStyleCommunication):
    ##
    # @brief start the server here
    def start_server(self):
        self.server = ModbusServerTCP(host=self.server_info["address"],
                                      port=int(self.server_info["modbus_port"]))
        self.server_thread = Thread(target=self.server.start, daemon=True)
        self.server_thread.start()

    ##
    # @brief start the server here
    def get_client(self) -> ModbusStyleClientBase:
        return ModbusClient(self.server_info["address"], int(self.server_info["modbus_port"]))