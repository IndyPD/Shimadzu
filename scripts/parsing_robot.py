import sys
import os


def extract_robot_fsm_lines(input_file):
    if not os.path.exists(input_file):
        print(f"❌ 파일을 찾을 수 없습니다: {input_file}")
        return

    output_file = f"robot_fsm_only_{os.path.basename(input_file)}"

    with open(input_file, 'r', encoding='utf-8') as infile, \
            open(output_file, 'w', encoding='utf-8') as outfile:

        count = 0
        for line in infile:
            if "[Robot FSM]" in line:
                outfile.write(line)
                count += 1

    print(f"✅ 완료: {count}개의 라인을 추출하여 {output_file}에 저장했습니다.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python3 parsing.py <로그파일이름.log>")
    else:
        extract_robot_fsm_lines(sys.argv[1])
