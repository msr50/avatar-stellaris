#!/usr/bin/env python3
'''
This is an Avatar script that tests the Avatar system with a simple vulnerable
firmware. Used as launchpad for everything.
'''

import os
import sys

import threading
import subprocess
import logging
import time
import serial

from avatar.system import System
from avatar.emulators.s2e import init_s2e_emulator
from avatar.targets.gdbserver_target import *
from avatar.targets.openocd_target import *
from avatar.targets.openocd_jig import *
from avatar.communicators.serial_communicator import *
from avatar.exploitgenerators.bufferoverflowgenerator import *

from collections import OrderedDict

log = logging.getLogger(__name__)

configuration = {
    "output_directory" : "/home/matthew/Workspace/COSC460/avatar-stellaris/small/log/",
    "configuration_directory" : os.getcwd(),
    "s2e" : {
        "s2e_binary" : "/home/matthew/Workspace/Debug/build/qemu-debug/arm-s2e-softmmu/qemu-system-arm",
        "verbose" : True,
        "emulator_gdb_path": "/usr/local/bin/arm-none-eabi-gdb",
        "klee" : {
        "batch-time" : 1.0,
        "use-batching-search" : "true",
        "use-concolic-execution" : "true",
        "use-random-path" : "true",
        },
        "plugins": OrderedDict([
            ("BaseInstructions", {}),
            ("Initializer", {}),
            ("FunctionMonitor", {}),
            ("ExecutionTracer", ""),
            ("TestCaseGenerator", "" ),
            ("InstructionTracer", ""),
            ("ArbitraryExecChecker", ""),
            ("MemoryInterceptor", {
                "verbose": True,
                "interceptors": {
                    "RemoteMemory": {
                        "ram": {
                            "range_start": 0x20000000,
                            "range_end": 0x20010000,
                            "priority": 0,
                            "access_type": ["read", "write", "execute", "io", "memory", "concrete_value", "concrete_address"]
                        }
                    }
                }
            }),
            ("RemoteMemory", {
                "verbose": True,
                "listen": "localhost:9999",
                "writeBack": False,
                "ranges": {
                    "ram": {
                        "address": 0x20000000,
                        "size": 0x10000,
                        "access": "rwx"
                    },
                    "rom": {
                        "address": 0x00000000,
                        "size": 0x40000,
                        "access": "rwx"
                    }
                }
            }),
            ("RawMonitor" , 
                """
                kernelStart = 0,
                length = {
                    delay      = false,
                    name       = "length",
                    start      = 0x00000740,
                    size       = 0x0000000E,
                    nativebase = 0x00000740,
                    kernelmode = true,
                },
                buffer = {
                    delay      = false,
                    name       = "buffer",
                    start      = 0x00000750,
                    size       = 0x0000001C,
                    nativebase = 0x00000750,
                    kernelmode = true
                },
                uartfun = {
                    delay      = false,
                    name       = "uartfun",
                    start      = 0x00000C52,
                    size       = 0x00000008,
                    nativebase = 0x00000C52,
                    kernelmode = true
                },
                vulnfun = {
                    delay      = false,
                    name       = "vulnfun",
                    start      = 0x00000BB8,
                    size       = 0x0000000C,
                    nativebase = 0x00000BB8,
                    kernelmode = true
                }
                """),
            ("ModuleExecutionDetector" ,
                """
                trackAllModules = true,
                configureAllModules = true,
                length = {
                  moduleName = "length",
                  kernelMode = true,
                },
                buffer = {
                  moduleName = "buffer",
                  kernelMode = true
                },
                uartfun = {
                  moduleName = "uartfun",
                  kernelMode = true
                },
                vulnfun = {
                  moduleName = "vulnfun",
                  kernelMode = true
                }
                """),
            ("Annotation" , 
                """
                length = {
                  module = "length",
                  active = true,
                  address = 0x00000748,
                  instructionAnnotation = "return_symbolic",
                  beforeInstruction = true,
                  switchInstructionToSymbolic = false
                },
                buffer = {
                  module  = "buffer",
                  active  = true,
                  address = 0x00000754,
                  instructionAnnotation = "buffer_symbolic_all",
                  beforeInstruction = true,
                  switchInstructionToSymbolic = false
                },
                uartfun = {
                  module  = "uartfun",
                  active  = false,
                  address = 0x00000C52,
                  callAnnotation = "uart_symbolic",
                  paramcount = 0
                },
                vulnfun = {
                  module  = "vulnfun",
                  active  = false,
                  address = 0x00000BB8,
                  callAnnotation = "vulnfunc_testcase",
                  paramcount = 1
                }
                """)
        ]),
        "include" : ["lua/functions.lua"]
    },
    "qemu_configuration": {
            "gdbserver": False,
            "halt_processor_on_startup": True,
            "trace_instructions": True,
            "trace_microops": False,
            "gdb": "tcp::1235,server,nowait",
            "append": ["-serial", "tcp::8888,server,nowait"]
        },
    "machine_configuration": {
            "architecture": "arm",
            "cpu_model": "cortex-m3",
            "entry_address": 0x00000af4,
            "memory_map": [
                {
                    "size": 0x00040000,
                    "name": "flash_firmware",
                    "file": "firmware/Release/Small.bin",
                    "map":  [{
                            "address": 0x00000000,
                            "type": "code",
                            "permissions": "rwx"
                            }]
                },
                {
                    "size": 0x00010000,
                    "name": "ram",
                    "map":  [{
                            "address": 0x20000000,
                            "type": "data",
                            "permissions": "rwx"
                            }]
                }
            ],
        },
    "avatar_configuration": {
        "target_gdb_address": "tcp:localhost:3333",
        "target_gdb_path": "/usr/local/bin/arm-none-eabi-gdb"
    },
    "openocd_configuration": {
        "config_file": "stellaris-openocd.cfg"
    }
}

class TargetLauncher(object):
    def __init__(self, cmd):
        self._cmd = cmd
        self._process = None
        self._thread = threading.Thread(target = self.run)
        self._thread.start()
        
    def stop(self):
        if self._process:
            self._process.kill()
            
    def run(self):
        self._process = subprocess.call(self._cmd)
    
class RWMonitor():
    def emulator_pre_read_request(self, params):
        log.info("Emulator is requesting read 0x%08x[%d]", params["address"], params["size"])
     
    def emulator_post_read_request(self, params):
        log.info("Executed read 0x%08x[%d] = 0x%x", params["address"], params["size"], params["value"])
    
    def emulator_pre_write_request(self, params):
        log.info("Emulator is requesting write 0x%08x[%d] = 0x%x", params["address"], params["size"], params["value"])
        pass
    
    def emulator_post_write_request(self, params):
        log.info("Executed write 0x%08x[%d] = 0x%x", params["address"], params["size"], params["value"])
        pass
    
    def stop(self):
        pass
        
        
        
        
def transfer_cpu_state_to_emulator(ava, debug=False, verbose=False):
    """  
    Transfers state from emulator to device, 
    Parameter:  avatar object
    Parameter: Debug:  stores state to a file
    Parameter: verbose : prints transfered state 
    """

    cpu_state = {}
    for reg in ["r0", "r1", "r2", "r3", 
                "r4", "r5", "r6", "r7", 
                "r8", "r9", "r10", "r11", 
                "r12", "sp", "lr", "pc", 
                "xPSR", "msp", "psp"]:
        value = ava.get_target().get_register(reg)
        cpu_state[reg] = hex(value)
        ava.get_emulator().set_register(reg, ava.get_target().get_register(reg))
        
    # This is to fix 16 / 32 bit thumb instruction issues
    ava.get_emulator().set_register("cpsr", ava.get_emulator().get_register("cpsr") | 0x20)

    if debug:
        f = open("cpu_state.gdb", "w")
        for (reg, val) in cpu_state.items():
            f.write("set $%s = %s\n" % (reg, val))
        f.close()
    if verbose:
        print("transfered CPU state to device: %s" % cpu_state.__str__())




def transfer_cpu_state_to_device(ava, debug=False, verbose=False):
    """    
    Transfers state from emulator to device, 
    Parameter: avatar object
    Parameter: Debug:  stores state to a file
    Parameter: verbose : prints transfered state    
    """

    cpu_state = {}
    for reg in ["r0", "r1", "r2", "r3", 
                "r4", "r5", "r6", "r7", 
                "r8", "r9", "r10", "r11", 
                "r12", "sp", "lr", "pc", 
                "xPSR", "msp", "psp"]:
        value = ava.get_emulator().get_register(reg)
        cpu_state[reg] = hex(value)
        ava.get_target().set_register(reg, ava.get_emulator().get_register(reg))
    if debug:
        f = open("cpu_state.gdb", "w")
        for (reg, val) in cpu_state.items():
            f.write("set $%s = %s\n" % (reg, val))
        f.close()
    if verbose:
        print("transfered CPU state to device: %s" % cpu_state.__str__())


def transfer_mem_to_target(ava, addr, length):
    """
    copies memory region to target
    """
    memory = ava.get_emulator().read_untyped_memory(addr, length)
    ava.get_target().write_untyped_memory(addr, memory)

def transfer_mem_to_emulator(ava, addr, length):
    """
    copies memory region to emulator
    """
    memory = ava.get_target().read_untyped_memory(addr, length)
    ava.get_emulator().write_untyped_memory(addr, memory)




print("OPENOCD: Creating OpenOCD Jig")
hwmon=OpenocdJig(configuration)

print("OPENOCD: Connecting to OpenOCD Target")
cmd = OpenocdTarget(hwmon.get_telnet_jigsock())

print("OPENOCD: Re-flashing image and setting breakpoint")
cmd.halt()
cmd.raw_cmd("flash write_image erase /home/matthew/Workspace/COSC460/avatar-stellaris/small/firmware/Release/Small.bin", True)
cmd.put_bp(0x00000737) # Run the target until init finishes
cmd.raw_cmd("reset", True)
cmd.wait()

print("AVATAR: Fetching configuration from target")
configuration = cmd.initstate(configuration)
del cmd

print("AVATAR: Loading Avatar")
avatar = System(configuration, init_s2e_emulator, init_gdbserver_target)
avatar.init()

print("AVATAR: Inserting Monitor")
avatar.add_monitor(RWMonitor())

print("AVATAR: Starting Avatar")
time.sleep(3)
avatar.start()

print("AVATAR: Transferring state from target to emulator")
transfer_mem_to_emulator(avatar, 0x20000000, 0x00001000)
print("AVATAR: Memory transfer complete")
transfer_cpu_state_to_emulator(avatar)
print("AVATAR: Register transfer complete")

print("AVATAR: Continuing emulation")
avatar.get_emulator().cont()

print("AVATAR: Completed firmware analysis")

print("Press enter to begin exploit generation")

keyboard = input ()

avatar.stop ()

print("EXPLOIT: Beginning automatic exploit generation")

# This section is run in two threads, since concurrency is important
# A thread is used to manage the target device, and another is used to 
# generate and send an exploit to the device.
# Lots of sleeps needed to be inserted since we are dealing with slow hardware

def device_thread ():
    print("EXPLOIT: Resetting device...")
    cmd = OpenocdTarget(hwmon.get_telnet_jigsock())
    time.sleep (3)
    cmd.halt ()
    # Remove the old breakpoint, and set a new one at the "ret" instruction
    # of the vulnerable function
    cmd.remove_bp (0x00000737)
    cmd.put_bp (0x00000bca)
    time.sleep (3)
    cmd.raw_cmd ("reset", True)
    print("EXPLOIT: Breakpoint should have been hit...")
    print("Check the value of PC")
    cmd.wait ()
    # We step into the "ret" instruction, and see the program counter changed
    cmd.raw_cmd ("step", True)
    cmd.dump_all_registers ()

def exploit_generator_thread ():
    print("EXPLOIT: Setting up serial conncetion to UART")
    uart = SerialCommunicator ("/dev/ttyUSB0", 38400, serial.EIGHTBITS, 
                               serial.PARITY_NONE, serial.STOPBITS_ONE)
    uart.connect ()
    print("EXPLOIT: Setting up stack buffer overflow exploit generator")
    overflow = BufferOverflowGenerator ()
    time.sleep (10)
    # Select what type of experiment we wish to attempt
    runtype = 0
    s2e_path = "log/s2e-last/s2e_stdout.log"
    payload = "generic_payload.txt"
    if runtype == 0:
        print("EXPLOIT: Setting input and payload values for testing")
        overflow.set_input ("I")
        overflow.set_payload ("AAAAAAAAAAAAAAAAAAAAdcbaA")
    elif runtype == 1:
        print("EXPLOIT: Passing S2E path info to ExploitGenerator to make exploit")
        overflow.construct_input (s2e_path)
        overflow.construct_payload (s2e_path, payload)
    elif runtype == 2:
        print("EXPLOIT: Generating input from S2E path and using generic payload")
        overflow.construct_input (s2e_path)
        f = open (payload, 'r')
        overflow.set_payload (f.read ().strip ())
        f.close ()
    print("EXPLOIT: Deploying exploit to device")
    overflow.deploy_exploit (uart)
    print("EXPLOIT: Saving exploit to file")
    f = open ("buffer_overflow.txt", 'w')
    f.write (overflow.get_exploit ())
    f.close ()
    time.sleep(5)
    uart.disconnect ()

# Create the threads
device_thread = threading.Thread (target=device_thread)
device_thread.start()

exploit_thread = threading.Thread (target=exploit_generator_thread)
exploit_thread.start()

# Wait for the threads to finish
exploit_thread.join()
device_thread.join()
print("Complete. Can quit now")
