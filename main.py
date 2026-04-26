from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import olefile
import zlib
import struct

app = FastAPI()

# 브라우저 허용 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_hwp_text(file_path):
    f = olefile.OleFileIO(file_path)
    
    # PrvText(미리보기 텍스트)는 문서 내용이 길 경우 중간에 잘리므로(일부만 저장됨)
    # 전체 텍스트를 가져오기 위해 항상 BodyText를 파싱합니다.
    dirs = f.listdir()
    body_sections = [d for d in dirs if d[0] == 'BodyText']
    full_text = ""
    
    for section in sorted(body_sections):
        stream = f.openstream("/".join(section))
        data = stream.read()
        
        try:
            unpacked = zlib.decompress(data, -15)
        except:
            unpacked = data
            
        i = 0
        while i < len(unpacked):
            header = struct.unpack("<I", unpacked[i:i+4])[0]
            length = (header & 0x3ff00000) >> 20
            record_type = header & 0x3ff
            
            if record_type == 67:
                text_data = unpacked[i+4:i+4+length]
                # HWP 텍스트 제어문자 처리 (깨진 한자 방지)
                idx = 0
                while idx < len(text_data):
                    if idx + 2 > len(text_data):
                        break
                    ch = struct.unpack("<H", text_data[idx:idx+2])[0]
                    if ch >= 32:
                        full_text += chr(ch)
                        idx += 2
                    elif ch in (10, 13):
                        full_text += '\n'
                        idx += 2
                    elif ch == 9:
                        full_text += '\t'
                        idx += 2
                    else:
                        # 16바이트 크기를 가지는 제어 문자들 (표, 그림 등)
                        if ch in (1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23):
                            idx += 16
                        else:
                            idx += 2
            
            i += 4 + length
            
    f.close()
    return full_text.strip()

@app.post("/extract")
async def extract_hwp(file: UploadFile = File(...)):
    import tempfile
    import os
    
    # 전송받은 파일 임시 저장 (Live Server 새로고침 방지를 위해 시스템 임시 폴더 사용)
    content = await file.read()
    fd, temp_name = tempfile.mkstemp(suffix=".hwp")
    
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    
    try:
        text = get_hwp_text(temp_name)
        os.remove(temp_name) # 사용 완료된 임시 파일 삭제
        return {"text": text}
    except Exception as e:
        if os.path.exists(temp_name):
            os.remove(temp_name)
        return {"text": f"파일 읽기 오류: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)