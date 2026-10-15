# bms2osu

BMS / BME / BML 채보를 **osu!mania** 채보(`.osu` / `.osz`)로 **일괄 변환**하는 도구입니다.
창(GUI)에서 폴더를 끌어다 놓고 버튼 한 번으로 변환합니다. (Python 3.9+, 드래그 앤 드롭은 `tkinterdnd2` 사용)

*English: a batch converter from BMS/BME/BML charts to osu!mania beatmaps with a drag & drop GUI. CLI: `python -m bms2osu --help`.*

## 사용법 (프로그램)

1. [Releases](https://github.com/hanjw0126/bms2osu/releases)에서 운영체제에 맞는 파일을 받아 실행합니다.
   - Windows: `bms2osu-windows.exe` / macOS: `bms2osu-macos.zip`(압축 해제 후 `bms2osu.app`) / Linux: `bms2osu-linux`
2. **BMS 폴더를 창으로 끌어다 놓습니다.** (여러 개 가능, 상위 폴더를 넣으면 하위 곡 폴더를 모두 찾음)
   드롭 영역을 클릭하거나 `폴더 추가...` 버튼으로 골라도 됩니다. 폴더를 exe 아이콘 위에 드롭해도 목록에 들어간 채로 열립니다.
3. 옵션 체크박스를 고른 뒤 **▶ 변환 시작**을 누르면 자동으로 변환됩니다. 진행률과 결과는 아래 로그에 표시됩니다.
4. 생성된 `.osz` 파일을 더블클릭하거나 osu! 창에 끌어다 놓으면 가져와집니다.

> macOS에서 처음 열 때 "확인되지 않은 개발자" 경고가 뜨면 앱을 우클릭 → **열기**를 선택하세요.

### 옵션 (체크박스)

| 체크박스 | 체크 시 | 체크 해제 시 (기본값) |
|---|---|---|
| 스크래치 제거 | **7키**(더블 14키) | **8키**(더블 16키) |
| 하위 폴더까지 검색 | 하위 폴더 전부 검색 (기본 켜짐) | 넣은 폴더만 검색 |
| .osz 패키지로 저장 | 오디오 포함 `.osz` (기본 켜짐) | 폴더에 `.osu` 파일로 저장 |
| 병렬 처리 | CPU 코어 수만큼 동시 변환 (기본 켜짐) | 한 폴더씩 변환 |
| 변환 후 출력 폴더 열기 | 끝나면 탐색기/Finder로 열기 (기본 켜짐) | 열지 않음 |
| 출력 폴더 지정 | 입력한 폴더 | `문서/bms2osu_output` |
| 제작자 이름 지정 | 입력한 이름 | `bms2osu` |
| OD / HP 직접 지정 | 입력한 값 (0~10) | 8 / 8 |
| 오디오 파일 지정 | 각 폴더 기준 파일명 | 폴더에서 가장 큰 오디오 자동 선택 |
| 인코딩 강제 지정 | 선택한 인코딩 | utf-8 → cp932 → cp949 순으로 자동 |

## 사용법 (명령줄)

GUI 없이 쓸 수도 있습니다. 소스에서 실행할 때는 인자 없이 `python -m bms2osu`를 실행하면 창이 열립니다.

```bash
pip install tkinterdnd2          # 드래그 앤 드롭용 (선택)
python -m bms2osu                # GUI
python -m bms2osu "D:/BMS/Songs" --remove-scratch -o out   # 명령줄
```

| 옵션 | 설명 |
|---|---|
| `--remove-scratch` | 스크래치 노트 제거 (7키 / 더블 14키) |
| `-o, --output DIR` | 출력 폴더 (기본 `./output`) |
| `--format osz\|osu` | `osz`(기본) / `osu` |
| `--audio NAME` | 오디오 파일명 또는 절대 경로 |
| `--creator NAME` | 채보 제작자 이름 |
| `--od N`, `--hp N` | OD / HP 값 (기본 8) |
| `--encoding ENC` | BMS 텍스트 인코딩 강제 지정 |
| `-j, --jobs N` | 병렬 처리 수 |
| `--no-recursive` | 폴더 하위 검색 안 함 |

## 변환 규칙

- BMS 파일이 들어 있는 **폴더 1개 = 비트맵셋(.osz) 1개**, 파일 1개 = 난이도 1개.
- 레인 배치(IIDX 방식): 스크래치 유지 시 `[스크래치][1~7]` (8키), 더블이면 `[스크][1~7][1~7][스크]` (16키).
- 지원: 마디 길이 변경(채널 02), BPM 변경(03 / 08), STOP(09), 롱노트(채널 5x/6x 및 `#LNOBJ`), `#RANDOM`(항상 1번 분기로 고정), 더블 플레이.
- BPM 변화는 osu! 타이밍 포인트로 기록됩니다. STOP은 노트 시간에 반영되지만 타이밍 그리드에는 표시되지 않습니다.

## 알려진 한계

- **키음 렌더링 미지원**: BMS는 노트마다 키음을 쓰지만 osu!는 곡 전체 오디오 1개를 재생합니다.
  키음을 하나로 믹싱한 오디오 파일(예: BMX2WAV 등으로 렌더링)을 같은 폴더에 두거나 `--audio`로 지정하세요.
  자동 선택은 폴더의 가장 큰 오디오 파일을 고르므로 결과를 꼭 확인하세요.
- BASE 62(`#BASE 62`), PMS(9키), 지뢰/히든 노트(채널 3x/Dx/Ex)는 지원하지 않습니다.
- 배경 이미지는 jpg/png만 포함됩니다. (osu!가 bmp를 지원하지 않음)
- 원작자의 허락 없이 변환한 곡을 osu!에 업로드/배포하지 마세요. 개인 플레이 용도를 권장합니다.

## 개발

```bash
python -m unittest discover -s tests -v
```

## GitHub 릴리즈 방법

1. GitHub에서 새 저장소를 만들고 이 폴더를 push 합니다.
   ```bash
   git init && git add . && git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/hanjw0126/bms2osu.git
   git push -u origin main
   ```
2. 버전 태그를 만들어 push 하면 **자동으로** 릴리즈가 만들어집니다.
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
3. GitHub Actions(`.github/workflows/release.yml`)가 테스트 후 Windows / macOS / Linux 실행 파일을 빌드하고,
   저장소의 **Releases** 페이지에 파일을 업로드합니다. (릴리즈 노트 자동 생성)

> 새 버전을 낼 때는 `pyproject.toml`과 `bms2osu/__init__.py`의 버전을 올린 뒤 새 태그를 push 하세요.
> 태그 없이 `main`에 `pyproject.toml` 변경을 push 하거나 Actions 탭에서 **Release** 워크플로를 수동 실행해도,
> `pyproject.toml`의 버전으로 `v<버전>` 태그와 릴리즈가 자동 생성됩니다.
