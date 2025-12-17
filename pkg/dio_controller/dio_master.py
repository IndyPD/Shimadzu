import threading

from ..utils.config_manager import ConfigManager
from ..utils.logging import Logger
from ..utils.blackboard import GlobalBlackboard
import sys
sys.path.append('dio_controller')
from .ethercat_client import *
import time

DIO_CONFIG_DEFAULT_PATH = "projects/frying_template/configs/dio_config.json"
bb = GlobalBlackboard()


class DIOMaster():
    def __init__(self, config_path=DIO_CONFIG_DEFAULT_PATH, period_s=0.05):
        """ Init. thread """
        self.running = False
        self.thread = None
        self.period_s = period_s

        self.di_data = []
        self.do_data = []

        self.config = ConfigManager(config_path=config_path)
        self.server_info = self.config.get("server")
        self.protocol = self.config.get("protocol")
        self.di_configs = self.protocol['di']
        self.do_configs = self.protocol['do']

        self.ecat = EtherCATClient(self.server_info["address"], self.server_info["port"])
              
        Logger.info("Init DIO_Master")

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

    def run(self):
        """ Thread's target function """
        while self.running:
            try:
                # print("dio_stat")
                # pyModbusTCP version compatible
                t0 = time.time()
                self.get_di_data()
                t1 = time.time()
                self.set_do_data()
                t2 = time.time()
                time.sleep(max(0.0, self.period_s - (t2 - t0)))
                # Logger.debug(f"Tact: {1000*(t1-t0):.1f} / {1000*(t2-t1):.1f} / {1000*(t2-t0):.1f}")
                bb.set("internal/dio_alive", 1)
            except Exception as e:
                bb.set("internal/dio_alive", 0)
                Logger.error("DIO Error")
                Logger.error(str(e))
                try:
                    self.ecat.disconnect()
                    time.sleep(0.5)
                    self.ecat.connect()
                finally:
                    time.sleep(0.5)

    def get_di_data(self):
        for config in self.di_configs:
            slave_index = config["slave_index"]
            channels = config["channels"]
            di_list = self.ecat.get_di(slave_index).di_list[:channels]
            for key, address in config['forwarding'].items():
                if isinstance(address, int):
                    bb.set(key, di_list[address])
                elif isinstance(address, list):
                    bb.set(key, [di_list[addr] for addr in address])
                else:
                    msg = "Invalid address type: {}".format(type(address))
                    Logger.error(msg)
                    raise(TypeError(msg))

    def set_do_data(self):
        for config in self.do_configs:
            slave_index = config["slave_index"]
            channels = config["channels"]
            current_do = self.ecat.get_do(slave_index).do_list[0:channels]
            for key, address in config['forwarding'].items():
                value = bb.get(key)
                if isinstance(address, int):
                    current_do[address] = value
                elif isinstance(address, list):
                    for addr, val in zip(address, value):
                        current_do[addr] = val
                else:
                    msg = "Invalid address type: {}".format(type(address))
                    Logger.error(msg)
                    raise(TypeError(msg))
            self.ecat.set_do(slave_index, current_do)
