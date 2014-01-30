#!/usr/bin/python

import time
import sys
import array

from PirateSWD import *
from SWDCommon import *
from EFM32 import *

def loadFile(path):
    arr = array.array('I')
    try:
        arr.fromfile(open(sys.argv[1], 'rb'), 1024*1024)
    except EOFError:
        pass
    return arr.tolist()

def main():
    busPirate = PirateSWD("/dev/ttyUSB0", vreg = True)
    debugPort = DebugPort(busPirate)
    efm32     = EFM32(debugPort)

    part_info = efm32.ahb.readWord(0x0FE081FC) # PART_NUMBER, PART_FAMILY, PROD_REV
    mem_info = efm32.ahb.readWord(0x0FE081F8)  # MEM_INFO_FLASH, MEM_INFO_RAM
    rev = (efm32.ahb.readWord(0xE00FFFE8) & 0xF0) | ((efm32.ahb.readWord(0xE00FFFEC) & 0xF0) >> 4) # PID2 and PID3 - see section 7.3.4 in reference manual
    rev = chr(rev + ord('A'))
    flash_size = mem_info & 0xFFFF
    family = part_info >> 16 & 0xFF
    print "Connected."
    page_size = 512
    if family == 71:
        print "Part number: EFM32G%dF%d (rev %c, production ID %dd)" % (part_info & 0xFF, 
                flash_size, rev, part_info >> 24 & 0xFF)
        family_s = "G"
    elif family == 72:
        print "Part number: EFM32GG%dF%d (rev %c, production ID %dd)" % (part_info & 0xFF, 
                flash_size, rev, part_info >> 24 & 0xFF)
        family_s = "GG"
        raise Exception("TODO read page size")
    elif family == 73:
        family_s = "TG"
        print "Part number: EFM32TG%dF%d (rev %c, production ID %dd)" % (part_info & 0xFF, 
                flash_size, rev, part_info >> 24 & 0xFF)
        raise Exception("TODO read page size")
    elif family == 74:
        family_s = "LG"
        print "Part number: EFM32LG%dF%d (rev %c, production ID %dd)" % (part_info & 0xFF, 
                flash_size, rev, part_info >> 24 & 0xFF)
        raise Exception("TODO read page size")
    elif family == 76:
        family_s = "ZG"
        print "Part number: EFM32ZG%dF%d (rev %c, production ID %dd)" % (part_info & 0xFF, 
                flash_size, rev, part_info >> 24 & 0xFF)
        page_size = 1024
    else:
        print "Warning: unknown part"
        sys.exit()
    print "Loading '%s'..." % sys.argv[1],
    vals = loadFile(sys.argv[1])
    with open(sys.argv[1], "rb") as f:
      data = f.read()
    size = len(vals) * 4
    print "%d bytes." % size
    if size / 1024.0 > flash_size:
        print "Firmware will not fit into flash!"
        sys.exit(1)

    efm32.halt()
    efm32.flashUnlock()
    print "Erasing Flash...",
    efm32.flashErase(flash_size, page_size)
    start_time = time.time()
    print "Programming Flash...",
    #efm32.flashProgram(vals)
    efm32.flashProgramWithFlashLoader(data, family_s)
    time_passed = time.time() - start_time
    print "Programmed %d bytes in %.2f seconds (%.2f kB/sec)." % (size,
            time_passed, (size / 1024.0) / time_passed)

    print "Resetting"
    efm32.sysReset()
    busPirate.tristatePins()

if __name__ == "__main__":
    main()
