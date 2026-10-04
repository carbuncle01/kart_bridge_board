# kart_bridge_board firmware steps

STM32G0B1CBT6用の段階別ファームウェアです。各ディレクトリの
`main.c`は、前段階の機能を残しながら一つずつ機能を追加します。

基板上の接続場所、ST-LINKの向き、macOSでのインストール、ビルド、
書き込み、Stepごとの配線変更を初めから順に進める場合は
[GETTING_STARTED.md](GETTING_STARTED.md)を参照してください。

> [!WARNING]
> このファームウェアは基板設計に合わせた初期実装です。実機での
> 書き込み、USB列挙、オシロスコープ確認はまだ完了していません。
> Step 5以降を車両で試す前に、必ずタイヤを浮かせ、モーターへの
> 電力を安全に遮断できる状態にしてください。

## ステップ

| ディレクトリ | 追加する機能 | MUX |
| --- | --- | --- |
| `step1_safe_boot` | MCU起動、PB4テストPWM | MANUAL固定 |
| `step2_usb_cdc` | USB CDCエコー | MANUAL固定 |
| `step3_rc_input` | RX1〜RX3 PWM測定 | MANUAL固定 |
| `step4_pwm_output` | PB4/PB5 PWM生成、`SET`コマンド | MANUAL固定 |
| `step5_manual_auto` | RC信号をMCU経由で再出力、明示的AUTO切替 | 条件付き |
| `step6_failsafe` | VBEC、USB、heartbeat、watchdog、RC喪失処理 | 条件付き |
| `step7_full_bridge` | USB指令によるサーボ／ESC制御 | 条件付き |
| `step8_final` | 受信機任意、CH3権限切替、通信断ラッチSAFEを統合した最終版 | 条件付き |

## 基板とのピン対応

| 機能 | MCUピン | 回路ネット |
| --- | --- | --- |
| RC CH1入力 | PA0 / TIM2_CH1 | `RX_CH1_MCU_N` |
| RC CH2入力 | PA1 / TIM2_CH2 | `RX_CH2_MCU_N` |
| RC CH3入力 | PA2 / TIM2_CH3 | `RX_CH3_MCU_N` |
| VBEC ADC | PA4 / ADC_IN4 | `VBEC_SENSE` |
| MANUAL/AUTO | PB0 | `SAFE_AUTO_SEL_MCU` |
| USB検出 | PB1 | `USB_PRESENT_N` |
| サーボPWM | PB4 / TIM3_CH1 | `MCU_SERVO_PWM_GPIO` |
| ESC PWM | PB5 / TIM3_CH2 | `MCU_ESC_PWM_GPIO` |
| USB D-/D+ | PA11 / PA12 | `USB_DM` / `USB_DP` |

Q1〜Q3でRC入力が反転されるため、入力キャプチャコードはMCU側Low期間を
受信機の正パルス幅として測定します。

## 必要なソフトウェア

- Arm GNU Toolchain (`arm-none-eabi-gcc`)
- CMake 3.22以降
- NinjaまたはMake
- ST公式`STM32CubeG0` v1.6.3以降
- 書き込み用STM32CubeProgrammer

macOSでの具体的なインストールコマンドは
[GETTING_STARTED.md](GETTING_STARTED.md#2-macへ必要なソフトを入れる)にあります。

STM32CubeG0はサブモジュールを含めて取得します。

```bash
git clone --recursive --depth 1 --branch v1.6.3 \
  https://github.com/STMicroelectronics/STM32CubeG0.git
```

## ビルド

リポジトリルートで次を実行すると最終版をReleaseビルドできます。

```bash
./firmware/scripts/build.sh             # step8_final
./firmware/scripts/build.sh all         # 全8段階
./firmware/scripts/test.sh              # ホスト単体テストとピン配置検査
```

`build.sh`は`STM32CUBE_G0_PATH`環境変数、未指定なら
`firmware/vendor/STM32CubeG0`を使用します。CMake・Ninja・Arm GNU Toolchainを
PATHへ用意してください。ローカル配置した`firmware/vendor/build-tools/bin`と
`firmware/vendor/arm-toolchain/bin`も自動検索します。
今回の作成先には依存ツールを配置済みです。`vendor/`はGit管理外なので、
別PCへcloneした場合は上記の必要なソフトウェアとSDKを取得してください。
SDKを既定位置に取得する場合は、リポジトリルートから次を実行します。

```bash
mkdir -p firmware/vendor
git clone --recursive --depth 1 --branch v1.6.3 \
  https://github.com/STMicroelectronics/STM32CubeG0.git firmware/vendor/STM32CubeG0
```

CMakeの段階選択変数は`KART_STEP`です。Cの`jpbb_*`/`JPBB_*`名、
Board ID `JPBB-01`、wire protocol `JPB1`は既存基板との互換性のため維持します。
USB製品表示名は`Kart Bridge Board`へ変更しています（VID/PIDは維持）。


例としてStep 1をビルドします。

```bash
cmake -S firmware -B firmware/build/step1 -G Ninja \
  -DKART_STEP=step1_safe_boot \
  -DSTM32CUBE_G0_PATH=/absolute/path/to/STM32CubeG0 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build firmware/build/step1
```

生成物は次の3形式です。

```text
firmware/build/step1/step1_safe_boot.elf
firmware/build/step1/step1_safe_boot.hex
firmware/build/step1/step1_safe_boot.bin
```

別の段階をビルドするときは、ビルドディレクトリと`KART_STEP`を変更します。

## 初回書き込み

1. 基板をJ6のUSB-CまたはJ5のBECから給電する。
2. ST-LINKをJ7へ接続する。J7 pin 1はVTrefであり給電入力ではない。
3. STM32CubeProgrammerでSWD接続する。
4. 初回のみ次のオプションバイトを設定し、読み戻して記録する。

```text
BOOT_LOCK = 0
nBOOT1    = 1
nBOOT_SEL = 0
```

5. 対象Stepの`.hex`または`.elf`を書き込む。
6. RESETを押し、対象Stepの確認手順を実施する。

オプションバイト設定後は、BOOTを押しながらRESETを押すことでSTM32内蔵
ROMのUSB DFUからも更新できます。

## USB CDCコマンド

Stepによって利用できるコマンドが増えます。

```text
PING
HEARTBEAT
STATUS
MANUAL
AUTO
SET <servo_us> <esc_us>
STREAM <servo_us> <esc_us>
HELP
```

`SET`と`STREAM`の許容値は両方とも1000〜2000 µsです。`SET`は確認応答を
返す対話用、`STREAM`はJoy／自動制御アプリケーションから連続送信する
応答なしの指令です。

Step 8のPC制御では、500 ms以内の`HEARTBEAT`に加えて、200 ms以内に
`SET`または`STREAM`が更新される必要があります。heartbeatだけが動き続け、
Joy／制御ループが停止した場合にも古い操作量を保持しないためです。

ホスト側bridgeとの互換通信には、これらの対話コマンドのほかCRC付き`JPB1`
フレームを100 Hzで使用します（Kart側bridgeの実装・接続は別途検証）。1フレームがheartbeatと指令更新を兼ね、
基板は20 HzでRC入力、実出力PWM、VBEC、選択経路、fault bitsを返信します。

車両で確認したESC極性に合わせ、JPB1の正規化指令はニュートラル1500 µsを
基準に、前進スロットルを1000 µs側、後進を2000 µs側へ変換します。
`brake`も前進中のESCブレーキを作動させるため2000 µs側へ変換します。
ブレーキ保持後に後進へ遷移する条件はESC固有なので、実車ではタイヤを浮かせて
ブレーキ／後進の切替シーケンスを確認してください。

### Step 8の推奨操作順

```text
PING
STATUS
SET 1500 1500
AUTO
STREAM 1500 1500
STREAM 1500 1500
...
MANUAL
```

簡易コンソールで試す場合は、最後に入力した`SET`を100 ms間隔の`STREAM`
として再送できます。

```bash
python3 firmware/tools/jpbb_serial_console.py \
  --port /dev/ttyACM0 --heartbeat --repeat-set
```

### Step 8の制御権

Step 8では「RCが接続されているか」ではなく、選択中の制御元が正常かを
監視します。

| 条件 | 制御権／出力 |
| --- | --- |
| CH3が1300 µs以下で安定、CH1/CH2有効 | RC直接経路 |
| CH3が1700 µs以上で安定、PCを明示的にアーム | PC/Joy/自動制御 |
| RC入力がすべてなく、PCを明示的にアーム | PC/Joy/自動制御 |
| 一度正常検出した受信機が消失 | SAFE値。受信機なし構成へ自動移行しない |
| RC制御中にCH1/CH2喪失 | SAFE値 |
| PC制御中に指令200 ms超過、heartbeat 500 ms超過、USB切断 | SAFE値 |
| VBEC異常または内部異常 | SAFE／ハードウェアMUX無効 |

CH3の1000/2000 µsとの完全一致は要求しません。1300〜1700 µsは
判定外帯とし、RC側は40 ms、PC側は100 msの連続確認後に確定します。
切替途中の判定外帯は100 msまで許容し、それ以上続けばSAFEへ移行します。
受信機が存在する場合、CH3のRC要求はPCのアームを解除する操作者優先の
オーバーライドです。受信機がない場合は、`SET`後の`AUTO`が明示的な
PCアームになります。PC制御のタイムアウトまたはUSB切断が一度発生すると
PCアームは解除されるため、通信復旧後も新しい`SET`と`AUTO`が必要です。

CH1〜CH3を一度すべて正常検出すると、その起動中は「受信機あり構成」として
ラッチします。その後に受信機全体が消失しても「受信機なしPC専用構成」へ
自動移行せず、SAFEへ移行します。受信機を外してPC専用構成へ変更する場合は、
外した状態で基板を再起動します。

`AUTO`というコマンド名は基板のMCU経路を選ぶ意味です。PC側の入力元は
Joyによる手動操作でも自動運転プログラムでも構いません。

ROS 2運用では、この意味を明確にするためJPB1のbit 1を`HOST_REQUEST`と
呼びます。CH3 Highはホスト経路を許可するだけで、Joy手動（MANUAL）と
自律走行（AUTO）の選択はKartのoperation mode／command mux側で行います。
command mux自体の変更は不要です。

USB切断後に再接続すると、ファームウェアはCRC付きニュートラルフレームを
受信して通信faultを解消できますが、自動では再アームしません。bridge nodeが
STOPを要求し、STOPからMANUALまたはAUTOを明示的に選び直した後にだけ、
ニュートラル・ハンドシェイクを経てホスト出力を再開します。

基板は`STREAM`の更新停止を検出できますが、Joy切断後もPCアプリケーションが
古い値を再送し続ける故障は識別できません。PC側でもJoyデバイス切断、入力時刻、
制御ループ周期、値の範囲を監視し、異常時は停止値を送るか送信を止めてください。

## 各Stepの確認

### Step 1

- USB-Cだけで基板を給電する。
- debuggerで`jpbb_step1_heartbeat`が1秒ごとに増えることを確認する。
- PB4のPWM幅が1400/1600 µsで交互に変化する。
- `SAFE_AUTO_SEL`はLowのままで、J4/J5はMANUAL経路を維持する。

### Step 2

- MacでUSB CDCポートが現れることを確認する。
- `PING`を送ると`PONG`が返る。
- 任意の行を送ると`ECHO ...`が返る。

### Step 3

- RX1〜RX3を接続する。
- USB CDCへ各チャンネルのパルス幅とvalid状態が250 msごとに出る。
- 受信機を切ると100 ms後にvalidが0になる。

### Step 4

- `SET 1500 1500`などを送る。
- PB4/PB5またはR22/R23のMCU側をオシロスコープで測定する。
- MUXはMANUAL固定なので、この段階ではJ4/J5の動作をAUTO確認に使わない。

### Step 5

- RX1/RX2がvalidのときだけ`AUTO`が受理される。
- AUTO中はMCUが測定したRX1/RX2幅をPB4/PB5へ再出力する。
- `MANUAL`またはRC異常でMANUALへ戻る。

### Step 6

- Step 5にVBEC、USB、heartbeat、watchdog監視を追加する。
- RC喪失時、VBECが正常なら1500/1500 µsをAUTO経路から出す。
- VBEC異常時はMANUALへ戻し、ハードウェアU5もMUXを無効化する。
- heartbeatまたはUSBが失われ、RCが正常ならMANUALへ戻る。

### Step 7

- 受信機使用時は、CH3のRC側で受信機直接操作、PC側でPC制御を許可する。
- 受信機なしでも、`SET`後に`AUTO`を送ればPC制御をアームできる。
- PC制御中は`SET`/`STREAM`を200 ms以内、`HEARTBEAT`を500 ms以内で送る。
- RC制御中のRC喪失と、PC制御中の指令停止／USB切断を別々に確認する。
- `STATUS`の`authority=RC/PC/SAFE`と`host_ready`で状態を確認する。

### Step 8

- 受信機なしでも、VBECとUSBが正常なら`SET`後の`AUTO`でPC制御をアームできる。
- 受信機ありでは、CH3の1300 µs以下をRC要求、1700 µs以上をPC許可として扱う。
- CH3をRC側へ切り替えるとPCアームを解除し、CH1/CH2をU2のMANUAL経路で直接通す。
- CH3をPC側へ戻しても自動再開せず、新しい`SET`と`AUTO`を必要とする。
- PC指令が200 ms、heartbeatが500 msを超えて更新されない場合は1500/1500 µsのSAFE出力へ移行し、PCアームを解除する。
- `STATUS`では`receiver=NONE/READY/NO_CH3/PARTIAL/LOST`と`failsafe=`理由を確認できる。

## USB VID/PID

開発中のUSB CDCはSTM32CubeのVCP例と同じ`0483:5740`を使用しています。
これは試作・開発確認用です。製品として配布する場合は、所有または利用許諾を
受けたVID/PIDへ変更してください。

## 現時点で未検証の項目

- STM32G0B1CBT6実機でのUSB列挙
- RC入力キャプチャのエッジ極性
- サーボ／ESCの3.3 V High認識
- MUX切り替え時のグリッチ
- VBEC ADC換算値と5.2〜8.5 V判定
- watchdogおよび全フェイルセーフ遷移
- 使用するESCで`JPBB_ESC_SAFE_US`が実際の停止値になること

2026-10-04にKart移行後の全Step 1〜8について、Arm GNU Toolchain 13.2.1と
STM32CubeG0 v1.6.3でReleaseビルドと`.elf` / `.hex` / `.bin`生成を確認しました。
制御・通信のホスト単体テストと静的配置検査もPASSです。
詳細、ビルド警告、生成物ハッシュは[移行記録](../docs/kart_migration.md)を参照してください。
これは実機での書き込み・動作確認を代替するものではありません。

これらが確認されるまでは車両を接地させた状態でAUTOを使用しないでください。
