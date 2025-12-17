# message_protocol.py
# 통신 메시지 형식 정의 및 처리 유틸리티

import json
from typing import Dict, Optional, Any

# 메시지 형식 정의 (Message Format Overview 탭 참고)
# STX (Start of Text): 0x02
# ETX (End of Text): 0x03
# 데이터 항목 구분자 (Record Separator): @

STX = chr(0x02)  # ASCII Start of Text
ETX = chr(0x03)  # ASCII End of Text
DATA_ITEM_SEPARATOR = "@"
ENCODING = 'utf-8'

# --- 메시지 생성 함수 ---
def create_message(message_type: str, parameters: Optional[Dict[str, Any]] = None) -> str:
    """
    주어진 메시지 타입과 파라미터를 사용하여 프로토콜 형식에 맞는 메시지 문자열을 생성합니다.
    형식: [STX]MessageType@Keyword1=Value1@Keyword2=Value2[ETX]
    
    Args:
        message_type: 메시지의 주 의미를 나타내는 문자열 (예: 'ARE_YOU_THERE', 'ANA_RESULT').
        parameters: 키워드-값 쌍의 딕셔너리.
        
    Returns:
        STX/ETX로 감싸진 완성된 메시지 문자열.
    """
    # 1. MessageType으로 시작
    message_parts = [message_type]
    
    # 2. 파라미터 추가 (Keyword=Value 형식으로, @로 구분)
    if parameters:
        for keyword, value in parameters.items():
            # 값은 문자열로 변환 (UI 사용을 위해 JSON 문자열화가 필요할 수 있음)
            if isinstance(value, dict) or isinstance(value, list):
                 # 복잡한 데이터 구조는 JSON 문자열로 변환하여 전송 (필요시)
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            message_parts.append(f"{keyword}={value_str}")
            
    # 3. 전체 메시지 문자열 구성
    message_body = DATA_ITEM_SEPARATOR.join(message_parts)
    
    # 4. STX와 ETX로 감싸기
    return f"{STX}{message_body}{ETX}"

# --- 메시지 파싱 함수 ---
def parse_message(raw_message: str) -> Optional[Dict[str, Any]]:
    """
    수신된 메시지 문자열을 파싱하여 MessageType과 파라미터 딕셔너리를 추출합니다.
    
    Args:
        raw_message: [STX]와 [ETX]를 포함하는 원본 메시지 문자열.
        
    Returns:
        'type'과 'params' 키를 가진 딕셔너리 또는 형식이 잘못된 경우 None.
    """
    try:
        # 1. STX와 ETX 제거 및 형식 검증
        if not (raw_message.startswith(STX) and raw_message.endswith(ETX)):
            print(f"[ERROR] Invalid message format: Missing STX/ETX. Message: {raw_message.encode('unicode_escape').decode()}")
            return None
            
        message_body = raw_message[1:-1]
        
        # 2. @ 구분자로 분리
        parts = message_body.split(DATA_ITEM_SEPARATOR)
        if not parts:
            print(f"[ERROR] Invalid message format: Empty body. Message: {raw_message.encode('unicode_escape').decode()}")
            return None
            
        # 3. MessageType 추출 (첫 번째 요소)
        message_type = parts[0]
        parameters: Dict[str, Any] = {}
        
        # 4. 파라미터 추출 (나머지 요소)
        for part in parts[1:]:
            if '=' in part:
                keyword, value = part.split('=', 1)
                
                # 값은 문자열로 유지하거나, JSON 형태로 전송된 경우 JSON 파싱을 시도할 수 있습니다.
                # 여기서는 UI에서 사용하기 쉽도록 일단 문자열로 파싱합니다.
                # 필요시 int/float 변환 로직 추가 가능
                
                # (옵션) JSON 파싱 시도
                try:
                    # JSON 문자열일 경우 파싱하여 dict/list로 저장
                    parsed_value = json.loads(value)
                    parameters[keyword] = parsed_value
                except json.JSONDecodeError:
                    # 일반 문자열일 경우 그대로 저장
                    parameters[keyword] = value

        return {
            "type": message_type,
            "params": parameters
        }

    except Exception as e:
        print(f"[ERROR] Failed to parse message '{raw_message[:50]}...'. Exception: {e}")
        return None

# --- 테스트 코드 (옵션) ---
if __name__ == '__main__':
    # 1. 메시지 생성 테스트: Korea -> Shimadzu (ASK_REGISTER 예시)
    params_client = {
        "TPNAME": "          TEST-A-001          ",
        "TYPE": "P",
        "SIZE1": "10.0000",
        "SIZE2": " 5.0000",
        "LOTNAME": "LOT-20250701-01"
    }
    client_msg = create_message("ASK_REGISTER", params_client)
    print(f"생성된 Client 메시지: {client_msg.encode('unicode_escape').decode()}")
    
    # 2. 메시지 파싱 테스트: Client 메시지 파싱
    parsed_client = parse_message(client_msg)
    print(f"파싱 결과 (Client): {parsed_client}")

    # 3. 메시지 생성 테스트: Shimadzu -> Korea (ANA_RESULT 예시)
    params_server = {
        "TPNAME": "          TEST-A-001          ",
        "VALUYP": "123.4567",
        "VALUTS": "500.0000",
        "VALUEPOS": " 25.500",
        "CODE": "00"
    }
    server_msg = create_message("ANA_RESULT", params_server)
    print(f"\n생성된 Server 메시지: {server_msg.encode('unicode_escape').decode()}")

    # 4. 메시지 파싱 테스트: Server 메시지 파싱
    parsed_server = parse_message(server_msg)
    print(f"파싱 결과 (Server): {parsed_server}")