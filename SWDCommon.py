import sys
import time

class DebugPort:
    ID_CODES = (
        0x1BA01477, # EFM32
        0x2BA01477, # STM32
        0x0BB11477, # NUC1xx
        0x0bc11477,  # EFM32-cortex-M0
        )
    def __init__ (self, swd):
        self.swd = swd
        # read the IDCODE
        # Hugo: according to ARM DDI 0316D we should have 0x2B.. not 0x1B.., but 
        # 0x1B.. is what upstream used, so leave it in here...
        idcode = self.idcode()
        if idcode not in DebugPort.ID_CODES:
            print "warning: unexpected idcode: ", hex(idcode)
        # power shit up
        self.swd.writeSWD(False, 1, 0x54000000)
        if (self.status() >> 24) != 0xF4:
            print "error powering up system"
            sys.exit(1)
        # get the SELECT register to a known state
        self.select(0,0)
        self.curAP = 0
        self.curBank = 0

    def idcode (self):
        return self.swd.readSWD(False, 0)

    def abort (self, orunerr, wdataerr, stickyerr, stickycmp, dap):
        value = 0x00000000
        value = value | (0x10 if orunerr else 0x00)
        value = value | (0x08 if wdataerr else 0x00)
        value = value | (0x04 if stickyerr else 0x00)
        value = value | (0x02 if stickycmp else 0x00)
        value = value | (0x01 if dap else 0x00)
        self.swd.writeSWD(False, 0, value)

    def status (self):
        return self.swd.readSWD(False, 1)

    def control (self, trnCount = 0, trnMode = 0, maskLane = 0, orunDetect = 0):
        value = 0x54000000
        value = value | ((trnCount & 0xFFF) << 12)
        value = value | ((maskLane & 0x00F) << 8)
        value = value | ((trnMode  & 0x003) << 2)
        value = value | (0x1 if orunDetect else 0x0)
        self.swd.writeSWD(False, 1, value)

    def select (self, apsel, apbank):
        value = 0x00000000
        value = value | ((apsel  & 0xFF) << 24)
        value = value | ((apbank & 0x0F) <<  4)
        self.swd.writeSWD(False, 2, value)

    def readRB (self):
        return self.swd.readSWD(False, 3)

    def readAP (self, apsel, address):
        adrBank = (address >> 4) & 0xF
        adrReg  = (address >> 2) & 0x3
        if apsel != self.curAP or adrBank != self.curBank:
            self.select(apsel, adrBank)
            self.curAP = apsel
            self.curBank = adrBank
        return self.swd.readSWD(True, adrReg)

    def writeAP (self, apsel, address, data, ignore = False):
        adrBank = (address >> 4) & 0xF
        adrReg  = (address >> 2) & 0x3
        if apsel != self.curAP or adrBank != self.curBank:
            self.select(apsel, adrBank)
            self.curAP = apsel
            self.curBank = adrBank
        self.swd.writeSWD(True, adrReg, data, ignore)

class MEM_AP:

    AP_CSW = 0
    AP_TAR = 1<<2 # 0x04
    AP_DRW = 3<<2 # 0x0C

    DHCSR = 0xE000EDF0
    DCRSR = 0xE000EDF4
    DCRDR = 0xE000EDF8
    DEMCR = 0xE000EDFC

    CoreDebug_DHCSR_S_REGRDY_Pos = 16
    CoreDebug_DHCSR_S_REGRDY_Msk = 1 << CoreDebug_DHCSR_S_REGRDY_Pos

    DHCSR_S_RESET_ST_Pos = 25
    DHCSR_S_RESET_ST_Msk = (1 << DHCSR_S_RESET_ST_Pos)

    DHCSR_S_HALT_Pos = 17
    DHCSR_S_HALT_Msk = 1 << DHCSR_S_HALT_Pos

    AP_CSW_32BIT_TRANSFER = 0x02
    AP_CSW_AUTO_INCREMENT = 0x10
    AP_CSW_MASTERTYPE_DEBUG = (1 << 29)
    AP_CSW_HPROT = (1 << 25)
    AP_CSW_DEFAULT = (AP_CSW_32BIT_TRANSFER | AP_CSW_MASTERTYPE_DEBUG | AP_CSW_HPROT)

    RUN_CMD = 0xA05F0001
    STOP_CMD = 0xA05F0003
    STEP_CMD = 0xA05F0005

    SCB_AIRCR = 0xE000ED0C
    SCB_AIRCR_VECTKEY_Pos = 16
    SCB_AIRCR_VECTRESET_Pos = 0
    SCB_AIRCR_VECTCLRACTIVE_Pos = 1
    SCB_AIRCR_VECTCLRACTIVE_Msk = (1 << SCB_AIRCR_VECTCLRACTIVE_Pos)
    SCB_AIRCR_VECTRESET_Msk = (1 << SCB_AIRCR_VECTRESET_Pos)



    def __init__ (self, dp, apsel):
        self.dp = dp
        self.apsel = apsel
        self.csw(1,2) # 32-bit auto-incrementing addressing

    def waitForRegReady(self):
      while (True):
        dhcsr = self.readWord(self.DHCSR)
        if dhcsr & self.CoreDebug_DHCSR_S_REGRDY_Msk:
          return

    def writeCpuReg(self, reg, value):
      # Wait until debug register is ready to accept new data
      self.waitForRegReady()
      # Write value to Data Register
      self.writeWord(self.DCRDR, value)
      # Write register number ot Selector Register. 
      # This will update the CPU register
      self.writeWord(self.DCRSR, 0x10000 | reg)

    def runTarget(self):
      self.writeWord(self.DHCSR, self.RUN_CMD)

    def csw (self, addrInc, size):
        """ Set control/status word register """
        self.dp.readAP(self.apsel, 0x00)
        csw = self.dp.readRB() & 0xFFFFFF00
        self.dp.writeAP(self.apsel, 0x00, csw + (addrInc << 4) + size)

    def idcode (self):
        self.dp.readAP(self.apsel, 0xFC)
        return self.dp.readRB()

    def readWord (self, adr):
        self.dp.writeAP(self.apsel, 0x04, adr)
        self.dp.readAP(self.apsel, 0x0C)
        return self.dp.readRB()

    def writeWord (self, adr, data):
        self.dp.writeAP(self.apsel, 0x04, adr)
        self.dp.writeAP(self.apsel, 0x0C, data)
        return self.dp.readRB()

    def writeAP(self, adr, data):
        self.dp.writeAP(self.apsel, adr, data)

    def readBlock (self, adr, count):
        self.dp.writeAP(self.apsel, 0x04, adr)
        vals = [self.dp.readAP(self.apsel, 0x0C) for off in range(count)]
        vals.append(self.dp.readRB())
        return vals[1:]

    def writeBlock (self, adr, data):
        self.dp.writeAP(self.apsel, 0x04, adr)
        for val in data:
            time.sleep(0.01)
            self.dp.writeAP(self.apsel, 0x0C, val)

    def writeBlockNonInc (self, adr, data):
        self.csw(0, 2) # 32-bit non-incrementing addressing
        self.dp.writeAP(self.apsel, 0x04, adr)
        for val in data:
            self.dp.writeAP(self.apsel, 0x0C, val)
        self.csw(1, 2) # 32-bit auto-incrementing addressing

    def writeHalfs (self, adr, data):
        """ Write half-words """
        self.csw(2, 1) # 16-bit packed-incrementing addressing
        self.dp.writeAP(self.apsel, 0x04, adr)
        for val in data:
            time.sleep(0.001)
            self.dp.writeAP(self.apsel, 0x0C, val, ignore = True)
        self.csw(1, 2) # 32-bit auto-incrementing addressing
