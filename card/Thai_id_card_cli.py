import datetime
import json
from smartcard.System import readers
from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.Exceptions import NoCardException
from smartcard.util import toHexString
from smartcard.scard import SCARD_PROTOCOL_T0, SCARD_PROTOCOL_T1, SCARD_SHARE_SHARED
import subprocess
import time
from datetime import datetime


class IDCardReader:
    
    def __init__(self):
        self.cardservice = None

    # ------------------- Helper Functions -------------------
    def decode_text(self, data):
        """แปลง bytes เป็น text"""
        try:
            return bytes(data).decode('tis-620', errors='ignore').strip()
        except:
            return ''.join(chr(b) if b < 128 else '?' for b in data).strip()

    def send_apdu_with_get_response(self, connection, apdu):
        """ส่ง APDU command และจัดการ GET_RESPONSE"""
        response, sw1, sw2 = connection.transmit(apdu)
        if sw1 == 0x61:
            get_response = [0x00, 0xC0, 0x00, 0x00, sw2]
            response, sw1, sw2 = connection.transmit(get_response)
        return response, sw1, sw2

    def parse_thai_date(self, date_str):
        """แปลงวันที่จากรูปแบบ YYYYMMDD เป็นรูปแบบที่อ่านง่าย"""
        if date_str == '99999999':
            return "ตลอดชีพ", "LIFELONG"
            
        if len(date_str) == 8 and date_str.isdigit():
            try:
                year = date_str[0:4]
                month = date_str[4:6]
                day = date_str[6:8]
                
                thai_year = int(year)
                eng_year = thai_year - 543
                
                thai_months = ['', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                            'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
                
                eng_months = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                            'July', 'August', 'September', 'October', 'November', 'December']
                
                month_int = int(month)
                if 1 <= month_int <= 12:
                    thai_date = f"{int(day)} {thai_months[month_int]} {thai_year}"
                    eng_date = f"{int(day)} {eng_months[month_int]} {eng_year}"
                    return thai_date, eng_date
            except Exception as e:
                print(f"[ผิดพลาด] แปลงวันที่ไม่สำเร็จ: {e}")
                return "ไม่ระบุ", "Not specified"
        else:
            return "ไม่ระบุ", "Not specified"

    def disconnect_card(self):
        """ตัดการเชื่อมต่อจากบัตร"""
        if self.cardservice:
            try:
                self.cardservice.connection.disconnect()
                print("[ตัดการเชื่อมต่อ] ตัดการเชื่อมต่อบัตรสำเร็จ")
            except Exception as e:
                print(f"[ผิดพลาด] ไม่สามารถตัดการเชื่อมต่อ: {e}")
            finally:
                self.cardservice = None

        # ------------------- Log Functions -------------------
    def save_to_log(self, data):
        """บันทึกข้อมูลลง log file"""
        log_file = "card_scan_log.json"
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data
        }
        try:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                    if not isinstance(logs, list):
                        logs = []
            except (FileNotFoundError, json.JSONDecodeError):
                logs = []
            logs.append(log_entry)
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=4)
            print(f"[Log] บันทึกข้อมูลลง {log_file} เรียบร้อย (รายการที่ {len(logs)})")
        except Exception as e:
            print(f"ไม่สามารถบันทึก log: {e}")
    # ------------------- Card Reader Functions -------------------
    def check_service_status(self):
        """ตรวจสอบสถานะ Smart Card Service"""
        try:
            result = subprocess.run(
                ["sc", "query", "SCardSvr"],
                capture_output=True, text=True, shell=True
            )
            return "RUNNING" in result.stdout
        except Exception as e:
            print(f"[ผิดพลาด] ตรวจสอบ Service ไม่สำเร็จ: {e}")
            return False

    def check_reader_status(self):
        """ตรวจสอบสถานะเครื่องอ่านบัตร"""
        if not self.check_service_status():
            print("[สถานะ] บริการ Smart Card ไม่ทำงาน")
            return False

        r = readers()
        if r:
            print(f"[สถานะ] พบเครื่องอ่านบัตร: {r[0]}")
            return True
        else:
            print("[สถานะ] ไม่พบเครื่องอ่านบัตร")
            return False

    # ------------------- Read ID Card -------------------
    def read_id_card(self):

        print("[Starting] กำลังอ่านข้อมูลบัตรประชาชน...")
        
        try:
            # ตัดการเชื่อมต่อเก่าก่อน (ถ้ามี)
            self.disconnect_card()
            
            # เชื่อมต่อกับบัตร
            cardtype = AnyCardType()
            cardrequest = CardRequest(timeout=5, cardType=cardtype)
            self.cardservice = cardrequest.waitforcard()
            
            print(f'\n[เชื่อมต่อ] เชื่อมต่อกับ: {self.cardservice.connection.getReader()}')
            
            try:
                self.cardservice.connection.connect(
                    protocol=SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1,
                    mode=SCARD_SHARE_SHARED
                )
                atr = self.cardservice.connection.getATR()
                print(f'[ATR] {toHexString(atr)}')
            except Exception as e:
                print(f"[ผิดพลาด] ไม่สามารถเชื่อมต่อบัตรได้: {e}")
                self.disconnect_card()
                return False
       
            # เลือก Thai ID card applet
            SELECT = [0x00, 0xA4, 0x04, 0x00, 0x08]
            THAI_ID_CARD = [0xA0, 0x00, 0x00, 0x00, 0x54, 0x48, 0x00, 0x01]
            response, sw1, sw2 = self.cardservice.connection.transmit(SELECT + THAI_ID_CARD)
            
            # จัดการ GET RESPONSE สำหรับ SW 61
            if sw1 == 0x61:
                print(f"[ข้อมูล] กำลังดึงข้อมูลเพิ่มเติม... (SW: {sw1:02x} {sw2:02x})")
                get_response = [0x00, 0xC0, 0x00, 0x00, sw2]
                response, sw1, sw2 = self.cardservice.connection.transmit(get_response)
            
            if sw1 != 0x90:
                print(f"[ผิดพลาด] ไม่สามารถเลือก Applet ได้ SW: {sw1:02x} {sw2:02x}")
                self.disconnect_card()
                return False
            
            print(f"[สำเร็จ] เลือก Thai ID Applet สำเร็จ (SW: {sw1:02x} {sw2:02x})")

            # คำสั่งอ่านข้อมูลต่างๆ
            commands = {
                'cid': [0x80, 0xb0, 0x00, 0x04, 0x02, 0x00, 0x0d],
                'name_th': [0x80, 0xb0, 0x00, 0x11, 0x02, 0x00, 0x64],
                'name_en': [0x80, 0xb0, 0x00, 0x75, 0x02, 0x00, 0x64],
                'birth': [0x80, 0xb0, 0x00, 0xD9, 0x02, 0x00, 0x08],
                'gender': [0x80, 0xb0, 0x00, 0xE1, 0x02, 0x00, 0x01],
                'issuer': [0x80, 0xb0, 0x00, 0xF6, 0x02, 0x00, 0x64],
                'issue_date': [0x80, 0xb0, 0x01, 0x67, 0x02, 0x00, 0x08],
                'expire_date': [0x80, 0xb0, 0x01, 0x6F, 0x02, 0x00, 0x08],
                'address': [0x80, 0xb0, 0x15, 0x79, 0x02, 0x00, 0x64],
                'request_number': [0x80, 0xB0, 0x16, 0x19, 0x02, 0x00, 0x0E]
            }

            print("\n" + "-"*70)
            print(" "*25 + "ข้อมูลบัตรประชาชน")
            print("-"*70)

            # อ่านเลขบัตรประชาชน
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['cid']
            )
            cid = self.decode_text(response)
            print(f"\n เลขบัตรประชาชน: {cid}")

            # อ่านชื่อ-นามสกุล (ไทย)
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['name_th']
            )
            name_th = self.decode_text(response).replace('#', ' ')
            print(f" ชื่อ-นามสกุล (ไทย): {name_th}")

            # อ่านชื่อ-นามสกุล (อังกฤษ)
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['name_en']
            )
            name_en = self.decode_text(response).replace('#', ' ')
            print(f" ชื่อ-นามสกุล (อังกฤษ): {name_en}")

            # อ่านวันเกิด
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['birth']
            )
            birth_raw = self.decode_text(response)
            birth_th, birth_en = self.parse_thai_date(birth_raw)
            print(f" วันเกิด (ไทย): {birth_th}")
            print(f" วันเกิด (อังกฤษ): {birth_en}")

            # อ่านเพศ
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['gender']
            )
            gender_code = self.decode_text(response)
            gender = "ชาย" if gender_code == "1" else "หญิง" if gender_code == "2" else gender_code
            print(f" เพศ: {gender}")

            # อ่านวันที่ออกบัตร
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['issue_date']
            )
            issue_raw = self.decode_text(response)
            issue_th, issue_en = self.parse_thai_date(issue_raw)
            print(f"\n วันที่ออกบัตร (ไทย): {issue_th}")
            print(f" วันที่ออกบัตร (อังกฤษ): {issue_en}")

            # อ่านวันหมดอายุ
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['expire_date']
            )
            expire_raw = self.decode_text(response)
            expire_th, expire_en = self.parse_thai_date(expire_raw)
            print(f" วันที่หมดอายุ (ไทย): {expire_th}")
            print(f" วันที่หมดอายุ (อังกฤษ): {expire_en}")
            
            # อ่านที่อยู่
            response, sw1, sw2 = self.send_apdu_with_get_response(
                self.cardservice.connection, commands['address']
            )
            address = self.decode_text(response).replace('#', ' ')
            print(f"\n ที่อยู่: {address}")

            data_to_save = {
                "cid": cid,
                "name_th": name_th,
                "name_en": name_en,
                "prefix_th": name_th.split()[0] if name_th else "",
                "first_name_th": name_th.split()[1] if len(name_th.split()) > 1 else "",
                "last_name_th": name_th.split()[2] if len(name_th.split()) > 2 else "",
                "prefix_en": name_en.split()[0] if name_en else "",
                "first_name_en": name_en.split()[1] if len(name_en.split()) > 1 else "",
                "last_name_en": name_en.split()[2] if len(name_en.split()) > 2 else "",
                "gender": gender,
                "birth_date_th": birth_th,
                "birth_date_en": birth_en,
                "address": address
            }
            

            # ตัดการเชื่อมต่อหลังจากอ่านเสร็จ
            self.save_to_log(data_to_save)
            photo_path = reader.read_photo()
            if photo_path:
                print(f"ไฟล์อยู่ที: {photo_path}")
            self.disconnect_card()
            
            print("[สำเร็จ]  อ่านข้อมูลบัตรประชาชนเรียบร้อยแล้ว")
            print("="*70 + "\n")
            return True
            
        except NoCardException:
            print("\n[Error] ไม่พบบัตรประชาชน กรุณาใส่บัตรแล้วลองใหม่")
            self.disconnect_card()
            return False
        except Exception as e:
            print(f"\n[Error] เกิดข้อผิดพลาดในการอ่านบัตร: {e}")
            self.disconnect_card()
            return False
        
    def read_photo(self):
        if not self.cardservice:
            print("[Error] ไม่พบการเชื่อมต่อบัตร")
            return None
    
        photo_bytes = bytearray()

        print("\n[Starting] กำลังอ่านรูปภาพจากบัตรประชาชน")

        APDU_PHOTO = [ 
            { 'key':'APDU_PHOTO1', 'apdu':[0x80, 0xb0, 0x01, 0x7B, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO2', 'apdu':[0x80, 0xb0, 0x02, 0x7A, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO3', 'apdu':[0x80, 0xb0, 0x03, 0x79, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO4', 'apdu':[0x80, 0xb0, 0x04, 0x78, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO5', 'apdu':[0x80, 0xb0, 0x05, 0x77, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO6', 'apdu':[0x80, 0xb0, 0x06, 0x76, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO7', 'apdu':[0x80, 0xb0, 0x07, 0x75, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO8', 'apdu':[0x80, 0xb0, 0x08, 0x74, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO9', 'apdu':[0x80, 0xb0, 0x09, 0x73, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO10', 'apdu':[0x80, 0xb0, 0x0A, 0x72, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO11', 'apdu':[0x80, 0xb0, 0x0B, 0x71, 0x02, 0x00, 0xFF] },
            { 'key':'APDU_PHOTO12', 'apdu':[0x80, 0xb0, 0x0C, 0x70, 0x02, 0x00, 0xFF] },
            { 'key':'APDU_PHOTO13', 'apdu':[0x80, 0xb0, 0x0D, 0x6F, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO14', 'apdu':[0x80, 0xb0, 0x0E, 0x6E, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO15', 'apdu':[0x80, 0xb0, 0x0F, 0x6D, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO16', 'apdu':[0x80, 0xb0, 0x10, 0x6C, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO17', 'apdu':[0x80, 0xb0, 0x11, 0x6B, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO18', 'apdu':[0x80, 0xb0, 0x12, 0x6A, 0x02, 0x00, 0xFF] }, 
            { 'key':'APDU_PHOTO19', 'apdu':[0x80, 0xb0, 0x13, 0x69, 0x02, 0x00, 0xFF] },
            { 'key':'APDU_PHOTO20', 'apdu':[0x80, 0xb0, 0x14, 0x68, 0x02, 0x00, 0xFF] }, 
        ]

        try:
            for part in APDU_PHOTO:
                response, sw1, sw2 = self.send_apdu_with_get_response(
                    self.cardservice.connection, part['apdu']
                )
                if sw1 == 0x90:
                    photo_bytes.extend(response)
                    print(f"[Photo] อ่าน {part['key']} สำเร็จ ({len(response)} bytes)")
                else:
                    print(f"[Photo] อ่าน {part['key']} ไม่สำเร็จ SW: {sw1:02X} {sw2:02X}")
                
            photo_file = "id_card_photo.jpg"
            with open(photo_file, "wb") as f:
                f.write(photo_bytes)
            print(f"[Success] บันทึกรูปภาพเรียบร้อย: {photo_file}")
            return photo_file
        except Exception as e:
            print(f"[Error] เกิดข้อผิดพลาดในการอ่านรูปภาพ: {e}")
            return None

    # ------------------- Main Loop -------------------
    def run(self):
        # ตรวจสอบเครื่องอ่านบัตรก่อน
        if not self.check_reader_status():
            print("\n[Error] ไม่พบเครื่องอ่านบัตร กรุณาเชื่อมต่อเครื่องอ่านบัตรแล้วรันโปรแกรมใหม่")
            return
        
        print("\n กรุณาใส่บัตรประชาชนเพื่ออ่านข้อมูล...")
        
        try:
            # อ่านบัตรครั้งเดียว
            if self.read_id_card():
                print("\n[Success] อ่านข้อมูลเสร็จสมบูรณ์")
            else:
                print("\n[Error] ไม่สามารถอ่านข้อมูลได้")
                
        except KeyboardInterrupt:
            print("\n\n[Cancel] ยกเลิกการอ่านข้อมูลโดยผู้ใช้")
        except Exception as e:
            print(f"\n[Error] เกิดข้อผิดพลาด: {e}")


# ------------------- Main -------------------
if __name__ == "__main__":
    try:
        reader = IDCardReader()
        reader.run()
    except KeyboardInterrupt:
        print("\n\nปิดโปรแกรมโดยผู้ใช้")
    except Exception as e:
        print(f"\n[Error] {e}")
    finally:
        print("="*70 + "\n")
