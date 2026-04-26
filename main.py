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
    
    # 1. 문서에 '미리보기 텍스트(PrvText)'가 있으면 이를 우선 사용합니다.
    # PrvText는 서식/제어문자가 모두 제거된 순수 텍스트(UTF-16LE)이므로 깨진 한자가 나오지 않습니다.
    if f.exists('PrvText'):
        stream = f.openstream('PrvText')
        data = stream.read()
        f.close()
        # 텍스트 추출 후 불필요한 공백/줄바꿈 정리
        return data.decode('utf-16le', errors='ignore').strip()
    
    # 2. PrvText가 없는 경우 기존 방식(BodyText 파싱) 사용
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
                full_text += text_data.decode('utf-16le', errors='ignore')
            
            i += 4 + length
            
    f.close()
    return full_text

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