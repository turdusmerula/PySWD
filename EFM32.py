from SWDCommon import *
import sys, array, time

class EFM32:
    RAM_START =      0x20000000
    STATE_LOCATION = 0x20000010
    FLASHLOADER_STATUS_NOT_READY = 0
    FLASHLOADER_STATUS_READY = 1

    def __init__ (self, debugPort):
        self.ahb = MEM_AP(debugPort, 0)

    #--------------------------------------------------------------------------
    # Cortex M3 stuff

    def halt(self):
        # halt the processor core
        self.ahb.writeWord(0xE000EDF0, 0xA05F0003)

    def unhalt(self):
        # unhalt the processor core
        self.ahb.writeWord(0xE000EDF0, 0xA05F0000)

    def run(self):
        # run the processor core
        self.ahb.writeWord(0xE000EDF0, 0xA05F0001)


    def sysReset(self):
        # restart the processor and peripherals
        self.ahb.writeWord(0xE000ED0C, 0x05FA0004)

    def reset_and_halt(self):
       self.halt()
       time.sleep(0.1)
       # Set halt-on-reset bit
       self.ahb.writeWord(self.ahb.DEMCR, 1);
       # Clear exception state and reset target
       self.ahb.writeAP(self.ahb.AP_TAR, self.ahb.SCB_AIRCR);
       self.ahb.writeAP(self.ahb.AP_DRW, (0x05FA << self.ahb.SCB_AIRCR_VECTKEY_Pos) |
                  self.ahb.SCB_AIRCR_VECTCLRACTIVE_Msk |
                  self.ahb.SCB_AIRCR_VECTRESET_Msk)

       # wait for reset
       dhcsr = 0x0
       timeout = 1000
       while True:
         dhcsr = self.ahb.readWord(self.ahb.DHCSR)
         timeout -= 1
         if not (dhcsr & self.ahb.DHCSR_S_RESET_ST_Msk):
           break
       
       print timeout, dhcsr
       time.sleep(0.1)
       if timeout == 0:
         raise Exception("timeout waiting for reset")
       # Verify that target is halted
       if not (dhcsr & self.ahb.DHCSR_S_HALT_Msk):
           raise Exception("not halted")

    #--------------------------------------------------------------------------
    # EFM32-specific stuff

    def flashUnlock (self):
        # unlock main flash
        self.ahb.writeWord(0x400C0000 + 0x008, 0x00000001) # MSC_WRITECTL.WREN <- 1

    def flashErase (self, flash_size, page_size):
        # erase page by page
        sys.stdout.write("   0.0 %") ; sys.stdout.flush()
        for i in range(flash_size * 1024 / page_size): # page size is 512 or 1024
            self.ahb.writeWord(0x400C0000 + 0x010, 0x200 * i)  # MSC_ADDRB <- page address
            self.ahb.writeWord(0x400C0000 + 0x00C, 0x00000001) # MSC_WRITECMD.LADDRIM <- 1
            self.ahb.writeWord(0x400C0000 + 0x00C, 0x00000002) # MSC_WRITECMD.ERASEPAGE <- 1
            while (self.ahb.readWord(0x400C0000 + 0x01C) & 0x1) == 1:
                pass # poll the BUSY bit in MSC_STATUS until it clears
            if i % 8 == 0:
                sys.stdout.write("\b" * 7)
                sys.stdout.write("%5.1f %%" % (100.0 * i / (flash_size * 2)))
                sys.stdout.flush()
        sys.stdout.write("\b" * 7 + "100.0 %\n")

    def flashProgram (self, vals):
        # Write each word one by one .... SLOOOW!
        # (don't bother with checking the busy/status bits as this is so slow it's 
        # always ready before we are anyway)
        sys.stdout.write("   0.0 %") ; sys.stdout.flush()
        addr = 0
        for i in vals:
            self.ahb.writeWord(0x400C0000 + 0x010, addr) # MSC_ADDRB <- starting address
            self.ahb.writeWord(0x400C0000 + 0x00C, 0x1)  # MSC_WRITECMD.LADDRIM <- 1
            self.ahb.writeWord(0x400C0000 + 0x018, i)    # MSC_WDATA <- data
            self.ahb.writeWord(0x400C0000 + 0x00C, 0x8)  # MSC_WRITECMD.WRITETRIG <- 1
            addr += 0x4
            if addr % 0x40 == 0:
                sys.stdout.write("\b" * 7)
                sys.stdout.write("%5.1f %%" % (25.0 * addr / len(vals)))
                sys.stdout.flush()
        sys.stdout.write("\b" * 7 + "100.0 %\n")

    def tar_wrap(self, family):
      if family in ['GG','LG','WG','G', 'TG']:
        return 0xFFF
      elif family in ['ZG']:
        return 0x3FF
      return 0x3FF

    def uploadFlashLoader(self, family):
        # target needs to be halted
        self.reset_and_halt()
        # set auto-increment
        tar_wrap = self.tar_wrap(family)
        #self.ahb.writeAP(self.ahb.AP_CSW, self.ahb.AP_CSW_DEFAULT | self.ahb.AP_CSW_AUTO_INCREMENT)
        self.ahb.writeAP(self.ahb.AP_CSW, self.ahb.AP_CSW_DEFAULT);
        addr = self.RAM_START
        arr = array.array('I')
        try:
          arr.fromfile(open('flashloader.bin', 'rb'), 1024*1024)
        except EOFError:
          pass
        flashloader = arr.tolist()
        print "flashloader words:", (len(flashloader))
        num = 0
        print "Writing flashloader"
        for i in flashloader:
          self.ahb.writeWord(addr, i)
          #if addr & tar_wrap == 0:
          #self.ahb.writeAP(self.ahb.AP_TAR, addr)
          #self.ahb.writeAP(self.ahb.AP_DRW, i)
          addr += 4
        self.ahb.writeAP(self.ahb.AP_CSW, self.ahb.AP_CSW_DEFAULT);
        print "Booting flashloader"
        # Load SP (Reg 13) from flashloader image
        self.ahb.writeCpuReg(13, flashloader[0])
        # Load PC (Reg 15) from flashloader image
        self.ahb.writeCpuReg(15, flashloader[1])
        self.run()

    def verifyFlashLoaderReady(self):
        retry = 1000
        status = self.FLASHLOADER_STATUS_NOT_READY
        while retry > 0 and status == self.FLASHLOADER_STATUS_NOT_READY:
          retry -= 1
          status = self.ahb.readWord(self.STATE_LOCATION)
        if status == self.FLASHLOADER_STATUS_READY:
          print "Flashloader is ready"
          return
        raise Exception("Flashloader not ready %d" % (status))
 
         
    def erasePagesWithFlashLoader(self, size):
        print "TODO erasePagesWithFlashLoader", size

    def uploadImageToFlashLoader(self, data):
        print "TODO uploadImageToFlashLoader"

    def flashProgramWithFlashLoader(self, data, family):
        self.uploadFlashLoader(family)
        self.verifyFlashLoaderReady()
        self.erasePagesWithFlashLoader(len(data))
        self.uploadImageToFlashLoader(data)
