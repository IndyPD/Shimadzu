import threading
import time
from abc import abstractmethod, ABC
from typing import List
import traceback

from ..utils.blackboard import GlobalBlackboard
from ..utils.config_manager import ConfigManager
from ..utils.logging import Logger
from ..utils.process_control import FlagDelay
import traceback
from pkg.configs.global_config import GlobalConfig

import json
global_config = GlobalConfig()


bb = GlobalBlackboard()


class AppCommunication(ABC):
    def start(self):
        """ Start the app communication thread """
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        """ Stop the app communication thread """
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()

    @abstractmethod
    def run(self):
        raise(NotImplementedError())

    @abstractmethod
    def receive_data_from_app(self):
        raise(NotImplementedError())

    @abstractmethod
    def send_data_to_app(self):
        raise(NotImplementedError())



class ModbusStyleCommunication(AppCommunication):
    client: 'ModbusStyleClientBase'

    def __init__(self, config_path, period_s=0.1, run_server=True):
        """ Init. thread """
        self.running = False
        self.thread = None
        self.period_s = period_s

        """ Init. config """
        self.config = ConfigManager(config_path=config_path)
        self.server_info = self.config.get("server")
        self.server_info["address"] = global_config.get("robot_ip")
        self.config.save_config()

        self.protocol = self.config.get("protocol")
        self.address_dict = self.get_address_dict(self.protocol)
        self.delayed_resets = {}
        for delayed_reset in self.protocol["delayed_resets"]:
            delay = delayed_reset["delay_seconds"]
            for idx in delayed_reset["indices"]:
                self.delayed_resets[idx] = FlagDelay(delay)
                bb.set(f"{self.address_dict[idx]}/expire", 0)

        """ Init. server """
        self.run_server = run_server
        if run_server:
            self.start_server()

        """ Init. modbus client """
        self.client = self.get_client()
        self.callback = lambda: None
        Logger.info("Init AppCommunication")

    @staticmethod
    def get_address_dict(protocol):
        address_dict = {}
        for key, address in protocol["read"]['forwarding'].items():
            bb.set(f"address/{key}", address)
            if isinstance(address, list):
                for addr in address:
                    address_dict[addr] = key
            else:
                address_dict[address] = key
        for key, address in protocol["write"]['forwarding'].items():
            bb.set(f"address/{key}", address)
            if isinstance(address, list):
                for addr in address:
                    address_dict[addr] = key
            else:
                address_dict[address] = key
        return address_dict

    ##
    # @param callback function to be called after reading data from app and before writing back
    def set_callback(self, callback):
        self.callback = callback

    ##
    # @brief start the server here
    @abstractmethod
    def start_server(self):
        raise(NotImplementedError())

    ##
    # @brief start the client here
    @abstractmethod
    def get_client(self) -> 'ModbusStyleClientBase':
        raise(NotImplementedError())

    def run(self):
        """ Thread's target function """
        while self.running:
            try:
                # pyModbusTCP version compatible
                t0 = time.time()
                self.receive_data_from_app()
                t1 = time.time()
                self.callback()
                t2 = time.time()
                self.send_data_to_app()
                t3 = time.time()
                time.sleep(max(0.0, self.period_s - (t3 - t0)))
                # Logger.debug(f"Tact(ms): {1000*(t1-t0):.1f} / {1000*(t2-t1):.1f} / {1000*(t3-t2):.1f} / {1000*(t3-t0):.1f}")
            except Exception as e:
                Logger.error(f"Error in {self.__class__.__name__}")
                Logger.error(str(e))
                traceback.print_exc()
                Logger.error(f"Try Reconnect to {self.__class__.__name__} client")
                self.client.check_reopen()

    def receive_data_from_app(self):

        """
        Receiving data from the app.
        """
        ranges = self.protocol['read']['ranges']
        addr0 = ranges[0][0]
        full_size = ranges[-1][-1] - addr0 + 1
        t0 = time.time()
        data = [0] * full_size
        for read_range in ranges:
            dat = self.client.get_ints(read_range[0], read_range[1] - read_range[0] + 1)
            if dat is not None:
                data[read_range[0] - addr0:read_range[1] - addr0 + 1] = dat

        for key, address in self.protocol['read']['forwarding'].items():
            if isinstance(address, int):                
                set_data= data[address-addr0]
                if address in [41, 51] :
                    if set_data :
                        Logger.info(f"App Send {key} {address} : {set_data}")
                    pass
                if address in [102, 110, 152] :
                    if set_data :
                        # Logger.info(f"App Send {key} {address} : {set_data}")
                        pass
                bb.set(key, set_data)
            elif isinstance(address, list):
                set_data= []
                for i in range(address[0],address[1]+1):
                    set_data.append(data[i-addr0])
                bb.set(key, set_data)
        
        
        for key, address in self.protocol['read_str']['forwarding'].items():
            str_data = self.client.get_string_with_id(address)
            # 수신된 문자열을 JSON으로 변환하여 출력
            try:
                json_data :dict = json.loads(str_data)
                data = json_data
                bb.set(key, data)
                # Logger.info(f"{key} {data}")

            except json.JSONDecodeError as e:
                # Logger.info(f"-----------------string -----------------\n {e}")
                bb.set(key, str_data)
        # Logger.debug("Read time: {:.1f}".format(1000*(time.time()-t0)))


    def send_data_to_app(self):
        """
        Sending data to the app.
        """
        # Attempt to send updated data to the app for each specified range

        ranges = self.protocol['write']['ranges']
        addr0 = ranges[0][0]
        full_size = ranges[-1][-1] - addr0 + 1
        data = [0] * full_size
        for key, address in self.protocol['write']['forwarding'].items():
            if isinstance(address, int):
                val = bb.get(key)       
                val_checked = self.check_reset(address, val, overwrite_address=False)
                data[address-addr0] = val_checked
                if val != val_checked:
                    bb.set(key, val_checked)

            elif isinstance(address, list):
                values = bb.get(key)
                values_checked = []
                for addr, val in zip(address, values):
                    val_checked = self.check_reset(addr, val, overwrite_address=False)
                    values_checked.append(val_checked)
                    data[addr-addr0] = val_checked
                if any([val != val_checked for val, val_checked in zip(values, values_checked)]):
                    bb.set(key, values_checked)
            else:
                msg = "Invalid address type: {}".format(type(address))
                Logger.error(msg)
                raise(TypeError(msg))
        t0 = time.time()
        for write_range in ranges:
            range0 = write_range[0]
            try:
                self.client.set_ints(range0, data[range0-addr0:write_range[1]-addr0+1])
            except Exception as e:
                print('grpc base : ',range0,' ',data[range0-addr0:write_range[1]-addr0+1])
                print('예외@@@@@@@@@ range ',range0,' : ',e)

        for key, address in self.protocol['read_reset']['forwarding'].items():
            if bb.get(key):
                if key == "ui/reset/pot1/btn" :
                    Logger.info("reset btn")
                elif key == "ui/reset/pot2/btn" :
                    Logger.info("reset btn")
                if key == "ui/reset/restart" :
                    Logger.info("reset restart")
                self.client.set_int(address,0)
                bb.set(key,False)

        for key, address in self.protocol['read_str_reset']['forwarding'].items():
            if bb.get(key):
                Logger.info(f"****************** {key} : {address}")
                self.client.set_string_with_id(address,'')
                bb.set(key,False)

    def check_reset(self, address, val, overwrite_address=True):
        if address in self.delayed_resets:
            expire_name = f"{self.address_dict[address]}/expire"
            overdelay = self.delayed_resets[address](val != 0)
            if val != 0 and (bb.get(expire_name) or overdelay):  # return 0 if expired or delay is over
                bb.set(expire_name, 0)  # reset expire if original value is down
                if overwrite_address:
                    self.client.set_int(address, 0)
                return 0
        return val

class ModbusStyleClientBase(ABC):
    ##
    # @brief write an int register at index
    # @param idx_ index of int value
    # @param val_ int value to write
    @abstractmethod
    def set_int(self, idx, val):
        raise(NotImplementedError())

    ##
    # @brief write an array of int registers starting from an index
    # @param idx_ starting index of int value
    # @param val_ int values to write
    @abstractmethod
    def set_ints(self, idx, val):
        raise(NotImplementedError())

    ##
    # @brief read an int register at index
    # @param idx index of int value
    @abstractmethod
    def get_int(self, idx) -> int:
        raise(NotImplementedError())

    ##
    # @brief write an array of int registers starting from an index
    # @param idx_ starting index of int value
    # @param val_ number of registers to read
    @abstractmethod
    def get_ints(self, idx, count) -> List[int]:
        raise(NotImplementedError())
    
    ##
    # @brief read an int register at index
    # @param idx index of int value
    @abstractmethod
    def set_string_with_id(self, idx, val) -> int:
        raise(NotImplementedError())

    ##
    # @brief write an array of int registers starting from an index
    # @param idx_ starting index of int value
    # @param val_ number of registers to read
    @abstractmethod
    def get_string_with_id(self, idx) -> List[int]:
        raise(NotImplementedError())

    ##
    # @brief disconnect client here. Need to be definitely FAIL-SAFE
    # @return True if connection was good
    @abstractmethod
    def check_reopen(self) -> bool:
        raise(NotImplementedError())
    
    


