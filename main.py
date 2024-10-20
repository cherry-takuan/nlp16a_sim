import re
import pprint
import alu_ref
import numpy as np
import sys
import time
#メモリ関連の構成
#シリアル等のメモリマップドデバイスはここに記述
class MEM:
    def __init__(self):
        self.ram  = np.zeros(64*1024, dtype=np.uint16)
    def MEM_RD(self,address):
        #print("MEM RD")
        return self.ram[address]
    def MEM_WR(self,address,data):
        #print("MEM WR")
        self.ram[address] = data

#CPU本体
class nlp16a:
    def __init__(self,MEM_RD,MEM_WR):
        self.MEM_RD = MEM_RD
        self.MEM_WR = MEM_WR
        #内部状態
        #self.ram  = np.zeros(64*1024, dtype=np.uint16)
        self.reg = np.zeros(0x14, dtype=np.uint16)
        self.int_enable = True
        self.REG_TABLE = {
            #RA1,RA2,RA3で再度レジスタにアクセスする際に使用
            0x00    :0x00,    0x01    :0x01,    0x02    :0x02,    0x03    :0x03,
            0x04    :0x04,    0x05    :0x05,    0x06    :0x06,    0x07    :0x07,
            0x08    :0x08,    0x09    :0x09,    0x0A    :0x0A,    0x0B    :0x0B,
            0x0C    :0x0C,    0x0D    :0x0D,    0x0E    :0x0E,    0x0F    :0x0F,
            #正規のレジスタ
            "IR1"   :0x00,    "IR2"   :0x01,    "IR3"   :0x03,    "IV"    :0x02,
            "FLAG"  :0x04,    "A"     :0x05,    "B"     :0x06,    "C"     :0x07,
            "D"     :0x08,    "E"     :0x09,    "F"     :0x0A,    "MEM"   :0x0B,
            "ADDR"  :0x0C,    "IP"    :0x0D,    "SP"    :0x0E,    "ZR"    :0x0F,
            #以下は特殊(実際のNLP-16Aでは上記のレジスタと同じようにはアクセスできないが，マイクロ命令を実装する上で簡単になるので加えた)
            "ACC"   :0x10,    "RA1"   :0x11,    "RA2"   :0x12,    "RA3"   :0x13
        }
        self.microinst_table = dict()
        self.microinst_file = "micro_inst.txt"
        self.alu = alu_ref.ALU()

    #マイクロ命令定義ファイルの読み込み
    def microinst_input(self)->dict:
        with open(self.microinst_file,encoding="utf_8") as f:
            inst_bin = 0x00
            inst_string = list()
            for s_line in f:
                s_line = s_line[:-1]
                if s_line == "" or s_line[0] == ";":
                    continue
                elif s_line[0] == "#":
                    if len(inst_string) != 0:
                        self.microinst_table[inst_bin] = inst_string
                    
                    inst_bin = int(s_line[1:],0)
                    #print(inst_bin,file=sys.stderr)
                    inst_string = list()
                else:
                    inst = re.split(r'\s+|->', s_line)
                    if len(inst) != 3:
                        print("不正なフォーマットです",file=sys.stderr)
                        exit(1)
                    inst_dict = dict()
                    inst_dict["type"] = inst[0]
                    inst_dict["from"] = inst[1]
                    inst_dict["to"] = inst[2]
                    inst_string.append(inst_dict)
        if len(inst_string) != 0:
            self.microinst_table[inst_bin] = inst_string
        return self.microinst_table
    #プログラム転送(別に必ず使う必要はない)
    def program_input(self,program_bin,start_address = 0):
        program_bin = list(program_bin)
        address = start_address
        while True:
            data = ""
            if len(program_bin) < 4:
                break
            data += program_bin.pop(0)
            data += program_bin.pop(0)
            data += program_bin.pop(0)
            data += program_bin.pop(0)
            try:
                data = int(data,16)
            except Exception as e:
                print("プログラム格納エラー",file=sys.stderr)
                print(e,file=sys.stderr)
                exit(1)
            else:
                #print("0x{:04X},".format(data),end="",file=sys.stderr)
                #self.ram[address] = data
                self.MEM_WR(address,data)
                address += 1
    #レジスタ読み書きのインターフェイス
    #MEMやRA1等のレジスタとして本当に触るわけではないものの処理
    def reg_read(self,reg_name):
        #print("RD:",reg_name)
        reg_num = self.REG_TABLE[reg_name]
        if reg_num == 0x0B:#MEM
            return self.MEM_RD(self.reg[0x0C])
        elif reg_num == 0x01:#RA1
            return self.reg[0x01]&0xFF
        elif reg_num == 0x11:#RA1
            #return self.reg[self.reg[0x00] & 0xF]
            return self.reg_read(self.reg[0x00] & 0xF)
        elif reg_num == 0x12:#RA2
            #return self.reg[self.reg[0x01] >>12]
            #print("RA2",self.reg[0x01] >>12)
            return self.reg_read(self.reg[0x01] >>12)
        elif reg_num == 0x13:#RA3
            #print("RA3",(self.reg[0x01] >>8) & 0xF)
            #return self.reg[(self.reg[0x01] >>8) & 0xF]
            return self.reg_read((self.reg[0x01] >>8) & 0xF)
        else:
            return self.reg[reg_num]
    def reg_write(self,reg_names,data):
        regs = reg_names.split(",")
        for reg_name in regs:
            #print("WR:",reg_name)
            reg_num = self.REG_TABLE[reg_name]
            if reg_num == 0x0B:
                self.MEM_RD(self.reg[0x0C],data)
            elif reg_num == 0x11:#RA1
                self.reg[self.reg[0x00] & 0xF] = data
            elif reg_num == 0x12:#RA2
                self.reg[self.reg[0x01] >>12] = data
            elif reg_num == 0x12:#RA3
                self.reg[(self.reg[0x01] >>8) & 0xF] = data
            else:
                self.reg[reg_num] = data
    #1命令実行
    def execute_inst(self):
        self.reg[0x0C] = self.reg[0x0D] #ADDR <- IP
        #self.reg[0x00] = self.ram[self.reg[0x0C]] # IR1 <- RAM[ADDR]
        self.reg[0x00] = self.MEM_RD(self.reg[0x0C]) # IR1 <- RAM[ADDR]
        inst = self.reg[0x00]>>8
        branch = (self.reg[0x00]>>4) & 0xF
        RA1 = self.reg[0x00] & 0xF
        print("\033[31m","{:04X},".format(self.reg[0x0D]),"inst","{:02X},".format(inst),"branch","{:01X},".format(branch),"RA1","{:01X},".format(RA1),"\033[0m",file=sys.stderr)
        self.reg[0x0D] += 1 #IP <- IP+1
        self.reg[0x0C] = self.reg[0x0D] # ADDR <- IP
        #1マイクロ命令を実行
        for micro_inst in self.microinst_table[inst]:
            print(micro_inst["type"]," : ",micro_inst["from"],"->",micro_inst["to"],file=sys.stderr)
            inst_type = micro_inst["type"].split(".")
            cond = ""
            if len(inst_type) == 2:
                func = inst_type[0]
                #print(inst_type[1])
                cond = inst_type[1]
            elif len(inst_type) == 1:
                func = inst_type[0]
            else:
                print("不正なマイクロ命令",file=sys.stderr)
                exit(1)
            inst_type = func.split("_")
            func_type = ""
            if len(inst_type) == 2:
                func = inst_type[1]
                #print(inst_type[0])
                func_type = inst_type[0]
            elif len(inst_type) == 1:
                func = inst_type[0]
            else:
                print("不正なマイクロ命令",file=sys.stderr)
                exit(1)

            result, Z, V, S, C = self.alu.ref_gen(self.reg_read(micro_inst["from"]),self.reg[0x10],func)#from (func) Acc -> to
            if cond != "3wd" or self.reg[0x12] == 0x03 or self.reg[0x13] == 0x03:#3wd命令ではないかもしくはRA2，RA3が3ワードモードである際に書き戻し
                if func_type == "F":#フラグモードならフラグを書き戻し
                    self.reg_write(micro_inst["to"],S<<3 | Z<<2 | V<<1 | C)
                else:
                    self.reg_write(micro_inst["to"],result)
            print("0x{:04X},".format(result))

            #want_value, Z, V, S, C = self.alu.ref_gen(self.reg_read())
        self.reg_viewer()
    #レジスタ表示
    def reg_viewer(self):
        for name in self.REG_TABLE.keys():
            try:
                dmy = int(name)
            except Exception:
                print(name,": [","{:04X}".format(self.reg[self.REG_TABLE[name]]),"]",end="",file=sys.stderr)
            else:
                continue
        print("",file=sys.stderr)
    #MEM表示
    #最後に使ったアドレス付近20を表示
    def ram_viewer(self):
        view_range = 20
        last_address = self.reg[self.REG_TABLE["ADDR"]]
        print("\nRAM===============",file=sys.stderr)
        bias = last_address-int(view_range/2)
        if last_address < view_range/2:
            bias = 0
        if last_address > 64*1024 - view_range/2:
            bias = 64*1024 - view_range
        for address in range(view_range):
            print("0x{:04X},".format(address+bias)," : 0x{:04X},".format(self.MEM_RD(address+bias)),end="",file=sys.stderr)
            if address+bias == last_address:
                print("  <--",file=sys.stderr)
            else:
                print("",file=sys.stderr)
        print("==================",file=sys.stderr)
if __name__ == "__main__":
    ram = MEM()
    cpu = nlp16a(ram.MEM_RD,ram.MEM_WR)
    cpu.microinst_input()
    cpu.program_input(sys.stdin.readline())
    cpu.ram_viewer()
    cpu.reg_viewer()
    while True:
        cpu.execute_inst()
        time.sleep(1)