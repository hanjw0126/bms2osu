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
| BMS 난이도 보정 | 난이도 이름·곡 제목·OD·HP를 BMS 정보로 자동 설정 (기본 켜짐) | 예전 방식 (`파일명 8K Lv.x`, OD/HP 8) |
| 키음을 하나의 음원으로 합성 | BMS 키음을 합쳐 `audio.ogg` 생성 (기본 켜짐, 권장) | 폴더의 오디오 파일을 그대로 사용 |
| 스크래치 제거 | **7키**(더블 14키) | **8키**(더블 16키) |
| 하위 폴더까지 검색 | 하위 폴더 전부 검색 (기본 켜짐) | 넣은 폴더만 검색 |
| .osz 패키지로 저장 | 오디오 포함 `.osz` (기본 켜짐) | 폴더에 `.osu` 파일로 저장 |
| 병렬 처리 | CPU 코어 수만큼 동시 변환 (기본 켜짐) | 한 폴더씩 변환 |
| 변환 후 출력 폴더 열기 | 끝나면 탐색기/Finder로 열기 (기본 켜짐) | 열지 않음 |
| 출력 폴더 지정 | 입력한 폴더 | `문서/bms2osu_output` |
| 제작자 이름 지정 | 입력한 이름 | `bms2osu` |
| OD / HP 직접 지정 | 입력한 값 (0~10) | 자동 (BMS 판정·게이지 기준, 보정을 끄면 8) |
| 오디오 파일 지정 | 각 폴더 기준 파일명 (키음 합성 대신 사용) | 키음 합성 결과 사용 |
| 인코딩 강제 지정 | 선택한 인코딩 | utf-8 → cp932 → cp949 순으로 자동 |

## 사용법 (명령줄)

GUI 없이 쓸 수도 있습니다. 소스에서 실행할 때는 인자 없이 `python -m bms2osu`를 실행하면 창이 열립니다.

```bash
pip install tkinterdnd2 numpy soundfile   # 드래그 앤 드롭 + 키음 합성용
python -m bms2osu                # GUI
python -m bms2osu "D:/BMS/Songs" --remove-scratch -o out   # 명령줄
```

| 옵션 | 설명 |
|---|---|
| `--remove-scratch` | 스크래치 노트 제거 (7키 / 더블 14키) |
| `-o, --output DIR` | 출력 폴더 (기본 `./output`) |
| `--format osz\|osu` | `osz`(기본) / `osu` |
| `--audio NAME` | 오디오 파일명 또는 절대 경로 (키음 합성 대신 사용) |
| `--no-keysound` | 키음 합성 끄기 (폴더의 오디오 파일 사용) |
| `--creator NAME` | 채보 제작자 이름 |
| `--od N`, `--hp N` | OD / HP 직접 지정 (기본: 자동) |
| `--no-difficulty-fix` | 난이도 보정 끄기 |
| `--encoding ENC` | BMS 텍스트 인코딩 강제 지정 |
| `-j, --jobs N` | 병렬 처리 수 |
| `--no-recursive` | 폴더 하위 검색 안 함 |

## 변환 규칙

- BMS 파일이 들어 있는 **폴더 1개 = 비트맵셋(.osz) 1개**, 파일 1개 = 난이도 1개.
- 레인 배치(IIDX 방식): 스크래치 유지 시 `[스크래치][1~7]` (8키), 더블이면 `[스크][1~7][1~7][스크]` (16키).
- 지원: 마디 길이 변경(채널 02), BPM 변경(03 / 08), STOP(09), 롱노트(채널 5x/6x 및 `#LNOBJ`), `#RANDOM`(항상 1번 분기로 고정), 더블 플레이.
- BPM 변화는 osu! 타이밍 포인트로 기록됩니다. STOP은 노트 시간에 반영되지만 타이밍 그리드에는 표시되지 않습니다.

## 난이도 보정

BMS의 난이도 정보를 osu!에 맞게 바꿔서 기록합니다.

| BMS | osu! | 방법 |
|---|---|---|
| `#DIFFICULTY`, 제목의 `[ANOTHER]` 같은 태그, 파일명(`_7a`, `-hyper` 등) | 난이도 이름 | `BEGINNER / NORMAL / HYPER / ANOTHER / INSANE / LEGGENDARIA` 중 하나로 판별 |
| `#PLAYLEVEL` | 난이도 이름 | `ANOTHER Lv.12`, 난이도표 표기(`★3`)는 그대로 `INSANE ★3` |
| `#TITLE`, `#SUBTITLE` | 곡 제목 | 난이도 태그를 지워서 모든 난이도가 같은 제목 하나로 묶이게 함 |
| `#RANK` / `#DEFEXRANK` (판정) | OD | VERY HARD 9 · HARD 8.5 · NORMAL 8 · EASY 7 · VERY EASY 6 |
| `#TOTAL` (게이지) | HP | 노트 수에 맞는 보통 TOTAL보다 후하면 HP를 낮게, 박하면 높게 (5~9.5) |

- 키 수(`8K`)는 osu!가 난이도 이름 앞에 `[8K]`로 직접 표시하므로 이름에서 뺐습니다.
- 난이도를 판별할 수 없으면 `Lv.5`처럼 레벨만, 이름이 겹치면 `Lv.5 (파일명)`처럼 구분합니다.
- **osu!의 별점(★)은 osu!가 노트를 보고 직접 계산**하므로 파일로 정할 수 없습니다. 그래서 BMS 레벨을 난이도 이름에 남기고, 태그(`BMS ANOTHER lv12` 등)에도 넣어 검색할 수 있게 했습니다.
- OD / HP를 직접 지정하면 그 값이 우선합니다.

## 키음 합성

BMS는 노트마다 키음(`#WAVxx`)을 재생하지만 osu!는 곡 전체 음원 1개만 재생합니다.
그래서 변환할 때 **BGM 채널(01)과 모든 노트의 키음을 정확한 시간에 배치해 하나의 `audio.ogg`로 합성**하고, 그 파일을 비트맵에 연결합니다.
노트와 같은 타임라인으로 계산하므로 싱크가 맞습니다.

- 롱노트는 시작할 때만 소리가 나고, 끝 지점(LN 끝, `#LNOBJ`)은 소리가 나지 않습니다.
- 같은 키음 번호가 다시 울리면 이전 소리를 끊습니다. (BMS 플레이어와 같은 방식)
- 스크래치를 제거해도 스크래치 키음은 음원에 그대로 남습니다.
- `#WAV01 kick.wav`인데 실제 파일이 `kick.ogg`인 경우처럼 확장자가 달라도 찾아내고, 대소문자도 구분하지 않습니다.
- `#VOLWAV` 볼륨을 반영하고, 소리가 깨지지 않게 최대 음량을 자동으로 맞춥니다.
- 난이도마다 키음 배치가 다르면 난이도별로 `audio.ogg`, `audio_2.ogg` …가 만들어지고, 같으면 한 파일을 공유합니다.
- 찾지 못한 키음 파일은 로그에 경고로 표시됩니다. 합성할 키음이 하나도 없으면 폴더의 오디오 파일을 대신 사용합니다.

## 알려진 한계

- osu!에서는 노트를 놓쳐도 키음이 그대로 재생됩니다. (음원이 하나로 합쳐져 있기 때문)
- 키음 합성은 곡 전체를 메모리에서 처리하므로, 아주 긴 곡이나 키음이 많은 곡은 변환에 몇 초 정도 걸릴 수 있습니다.
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
