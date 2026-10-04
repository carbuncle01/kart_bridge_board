# JPBB-HW-DEF-001 — Rev.1設計・発注レビュー

| 項目 | 定義 |
| --- | --- |
| 正式名称 | `kart_bridge_board` |
| Board ID | `JPBB-01` |
| Revision | `Rev.1` |
| 文書日付 | 2026-07-22 |
| 基板外形 | 60 × 30 mm |
| 基板構成 | 4層、1.0 mm |
| 積層 | JLCPCB `JLC3313` |
| 表面処理 | ENIG |
| PCBA | JLCPCB、Top-side実装 |

この文書は、KiCad設計とJLCPCB発注内容を照合するための実務チェック資料です。在庫、価格、JLCPCBの製造条件は固定値ではないため、注文時点の表示を最終判断に使用してください。

## 1. Rev.1で確定した構成

- 受動SMD部品のうち、抵抗とセラミックコンデンサは0402（1005 metric）です。
- C1はPanasonic `EEHZK1E101UP`（100 µF / 25 V、6.3 × 5.8 mm、導電性高分子ハイブリッドアルミ電解）で、VBECの唯一のオンボード・バルクコンデンサです。
- 追加バルク用C2は削除済みで、フットプリントもありません。
- USBはSTM32G0B1内蔵HSI48を使用し、USB SOFを基準とするCRSで同期する方針です。
- 外部HSE水晶Y1と負荷コンデンサC12/C13は削除済みで、MCUの該当ピンは未使用です。
- テストポイントはTP1〜TP8だけです。TP9〜TP12は削除済みです。
- PCBAはTop sideのみです。B面に実装部品は置きません。
- KiCadの積層はJLCPCB `JLC3313`、4層・1.0 mm、表面処理ENIGで確定しています。発注画面でも同じ積層を明示的に選択します。
- J1〜J5だけをDNPとしてPCBA後にヘッダーを手はんだします。J7、SW1、SW2はTop-side PCBA実装です。
- H1/H2は削除済みです。固定はB面中央の20 × 12 mm平坦領域へ両面テープで行います。
- D1/D2でVBECとUSB VBUSを`LOGIC_RAW`へダイオードORし、U3で+3V3を生成します。USB単独でもMCUとUSB周辺は起動しますが、VBEC、U2、サーボ、ESCには給電しません。
- U5はVBECを監視し、VBECがTMUX7236の有効範囲へ達するまでMUXを無効化します。

発注用BOMやCPLに`C2`、`Y1`、`C12`、`C13`、`H1`、`H2`、`TP9`〜`TP12`が現れる、またはJ7/SW1/SW2が存在しない場合は古い出力です。注文せず、最終設計から製造データを再生成してください。

## 2. フェイルセーフの保証境界

| 状態 | Rev.1の動作と保証範囲 |
| --- | --- |
| MCU正常・RC正常 | MANUALを既定とし、全AUTO条件成立時だけMCU生成PWMへ切り替える |
| MCU正常・RC消失 | ファームウェアが安全PWMを生成し、MUXをMCU側へ切り替えることでニュートラル／中央を指示する |
| MCU異常・RC正常 | `SAFE_AUTO_SEL`の10 kΩプルダウンにより、ハードウェアでMANUALへ戻す |
| MCU異常・RC消失 | 有効なRCパルスがないため、受信機、ESC、サーボ自身の信号喪失動作に依存する |
| VBEC低下 | U5がTMUXのENをLowへ保持して信号出力を無効化する。閾値付近およびサーボ／ESC電源不足時の動作は実機確認が必要 |

「MCU異常とRC消失の同時発生」まで独立してニュートラル化する回路ではありません。この状態も基板単体で保証するには、独立セーフティMCUまたは独立パルス生成回路が必要です。

ファームウェアでは次を満たしてください。

- 起動直後は`SAFE_AUTO_SEL = Low`を維持し、入力キャプチャ、PWM、watchdog、USBを初期化した後にだけAUTOを許可する。
- RC消失時にESCニュートラルPWMとステアリング中央PWMを出し、AUTO許可フラグは解除する。
- heartbeat停止、USB切断、指令範囲外、VBEC異常、内部異常ではMANUALまたは明示した安全状態へ遷移する。
- MUX切り替えは両PWMがLowのフレーム間で行い、短パルスを避ける。

## 3. 主要部品と発注時照合

| Ref | メーカー型番 | LCSC | 実装 |
| --- | --- | --- | --- |
| U1 | STM32G0B1CET6 | C5270267 | PCBA。品番とLCSC番号を両方確認 |
| U2 | TMUX7236PWR | C37096021 | PCBA。在庫が少ない可能性があるため、発注直前の在庫確認・確保を必須とする |
| U3 | MCP1703AT-3302E/CB | C144183 | PCBA |
| U4 | USBLC6-2SC6 | C7519 | PCBA |
| U5 | HX61CN5002MR | C47344213 | PCBA。5.0 V品、open-drain出力、SOT-23のpin 1を確認 |
| D1, D2 | 1N4148W | C84367 | PCBA。pin 1（cathode）が`LOGIC_RAW`側 |
| J6 | TYPE-C-31-M-12 | C165948 | PCBA |
| Q1〜Q4 | MMBT3904LT1G | C81464 | PCBA |
| C1 | EEHZK1E101UP、100 µF / 25 V | C454668 | PCBA、極性と専用ランドを確認 |
| J1〜J5 | 1×3、2.54 mmヘッダー | — | DNP、PCBA後に手はんだ |
| J7 | FTSH-105-01-L-DV-007-K | C5296739 | PCBA。Cortex SWD、物理position 7なし、VTrefは参照入力 |
| SW1, SW2 | TS-1088-AR02016 | C720477 | PCBA。SW1=RST、SW2=BOOT |

0402の標準受動部品は次の対応です。LCSC番号が変更・廃止されている場合は、同じ値だけで置換せず、サイズ、耐圧、誘電体、許容差も確認してください。

| 値 | メーカー型番 | LCSC | 使用種別 |
| --- | --- | --- | --- |
| 0 Ω | 0402WGF0000TCE | C17168 | 抵抗 |
| 1 kΩ | 0402WGF1001TCE | C11702 | 抵抗 |
| 5.1 kΩ | 0402WGF5101TCE | C25905 | 抵抗 |
| 10 kΩ | 0402WGF1002TCE | C25744 | 抵抗 |
| 22 kΩ | 0402WGF2202TCE | C25768 | 抵抗 |
| 47 kΩ | 0402WGF4702TCE | C25792 | 抵抗 |
| 100 kΩ | 0402WGF1003TCE | C25741 | 抵抗 |
| 1 MΩ | 0402WGF1004TCE | C26083 | 抵抗 |
| 10 nF / 50 V / X7R | CL05B103KB5NNNC | C15195 | セラミックコンデンサ |
| 100 nF / 16 V / X7R | CL05B104KO5NNNC | C1525 | セラミックコンデンサ |
| 1 µF / 25 V / X5R | CL05A105KA5NQNC | C52923 | セラミックコンデンサ |

LCSC在庫、Basic/Extended区分、最小注文数、価格は発注時点で変わり得ます。代替部品は、メーカー型番、ピン配置、パッケージ、動作電圧、絶対最大定格、受動部品の耐圧・誘電体を回路図とデータシートの両方で照合してください。

## 4. 電源と熱

- J5 pin 2をVBEC入力源とし、J1〜J4 pin 2、TMUX7236、C1へ直接分配します。VBECはD1を通って`LOGIC_RAW`も給電します。
- USB VBUSは`USB_VBUS_SENSE_ONLY`からD2を通って`LOGIC_RAW`を給電し、同時にUSBLC6-2SC6 pin 5とQ4検出回路へ接続します。D1/D2によりUSB VBUSとVBECを相互に逆流させません。
- U3は`LOGIC_RAW`から+3V3を生成します。USB単独時に+3V3が約3.3 Vへ上昇するのは意図した動作ですが、VBECは0 V付近、U2／サーボ／ESCは無給電でなければなりません。
- BEC単独時はUSB VBUSが0 V付近であることを確認します。USBとBECの同時接続時も、PC側VBUSやVBECへ意図しない逆流がないことを電圧・電流で確認します。
- U5はVBEC監視専用です。VBECが規定域へ達するまではopen-drain出力で`MUX_ENABLE_OK`をLowにし、TMUX7236を無効化します。
- MCP1703AのSOT-23A配列はpin 1 GND、pin 2 VOUT、pin 3 VINです。JLCPCBの部品照合画面で回転とpin 1を確認します。
- C1の100 µFだけで、使用サーボの突入・ストール時VBECを保証することはできません。問題が出た場合は外付け低ESR容量、配線、BEC、サーボ選定を含めて再評価してください。Rev.1には追加実装用C2はありません。
- D1/D2の順方向電圧後にU3へ入るため、LDO損失は実測した`LOGIC_RAW`と+3V3の差に3V3電流を掛けて評価します。50〜100 mA級ではD1/D2とU3の両方の温度・電圧降下を測り、余裕がなければSchottky／理想ダイオードまたは降圧電源へ変更します。
- VBEC監視は100 kΩ / 22 kΩと10 nFです。ADCノードは6 V入力時約1.082 V、8 V入力時約1.443 V、16 V入力時約2.89 Vです。元の100 kΩ / 68 kΩ例とは換算係数が異なるため、ファームウェアは実装値を使用します。ADCは長いサンプリング時間を使い、抵抗公差と電源異常を含めてしきい値を決めます。
- BECの公称6 V / 1.5 Aは系全体の能力上限です。基板配線だけでなく、受信機、サーボ、コネクタ、ケーブルを含む電流経路を実測します。
- Rev.1のVBEC入力には逆接保護、ヒューズ／電子過電流保護、車載サージ用TVSがありません。J5の極性を治具で確認し、必要な保護は上流側へ設けます。
- J1〜J5のpin 2は同じVBECネットです。J5のBECと独立した受信機電源など、複数の電源を同時接続しません。
- MCUからMUXへ入るPWMは3.3 V振幅です。採用するサーボとESCが3.3 V Highを確実に認識することを、量産発注前に最低・最高VBEC、温度、ケーブル長を含めて実機確認します。

## 5. USBクロックと差動配線

Rev.1は外部水晶を使用しません。ファームウェアでHSI48とCRSを有効にし、USB SOFへ同期させることがUSB CDC動作の前提です。Y1/C12/C13を後から実装して解決するためのフットプリントはありません。

Rev.1のKiCad積層は次のJLCPCB `JLC3313`対称構成です。

| 順序 | 層／材料 | 厚さ |
| --- | --- | ---: |
| 1 | F.Cu（外層銅） | 35 µm |
| 2 | 3313 prepreg | 0.0994 mm |
| 3 | In1.Cu（内層銅） | 15.2 µm |
| 4 | NP-155F core | 0.700 mm |
| 5 | In2.Cu（内層銅） | 15.2 µm |
| 6 | 3313 prepreg | 0.0994 mm |
| 7 | B.Cu（外層銅） | 35 µm |

仕上がり厚は1.0 mm、表面処理はENIGです。基板ファイルの`USB_DIFF`は線幅0.15 mm / 間隔0.15 mmですが、これは名目設計値であって90 Ω差動を保証する値ではありません。JLCPCB発注画面で必ず同じ`JLC3313`を選び、公式インピーダンス計算機と注文時DFMへ最終Gerberの条件を入力して再確認します。計算結果またはDFM指示と異なる場合は、配線と製造指定を整合させてから製造データを再生成します。

- D+/D−はF.Cu主体で短く配線する。USB-Cの同名A/Bパッド接続などでビアが必要な場合は、ペアで同じ個数・形状に揃え、遷移部とリターン経路を最終Gerberで確認する。
- 直下のIn1.Cuは連続したGNDとし、スリットや分断を作らない。
- USBLC6-2SC6はUSB-C直後に置き、分岐スタブを作らない。
- MCU直列抵抗R5/R6は0 Ω実装を初期値とする。
- USBデータ線へテストポイントを追加しない。
- USBだけを接続した状態で、VBECが0 V付近、`LOGIC_RAW`がVBUSからD2の順方向電圧を引いた値、+3V3が約3.3 Vになることを初回通電時に測定する。

### 初回SWD設定とUSB DFU

J7はArm Cortex 10-pin SWD準拠のSamtec `FTSH-105-01-L-DV-007-K`です。物理position 7が存在しないため、逆挿ししにくい構成です。主な接続はpin 1 VTref、pin 2 SWDIO、pin 3/5/9 GND、pin 4 SWCLK/BOOT0、pin 10 NRSTです。pin 1はST-LINKがターゲット電圧を読むための参照であり、基板への給電入力として扱いません。

初回は基板をUSB-CまたはBECで給電してST-LINKをJ7へ接続し、STM32CubeProgrammerで次を設定します。

```text
BOOT_LOCK = 0
nBOOT1    = 1
nBOOT_SEL = 0
```

`nBOOT_SEL`がRM0444上の正しい名称です。`nBOOT0_SEL`とは記載しません。この設定ではリセット立ち上がり時のPA14-BOOT0レベルを使用し、BOOT=Highかつ`nBOOT1=1`でSystem memoryを選びます。

以後のUSB DFU手順は次です。

1. MacへUSB-Cで接続する。
2. SW2（BOOT）を押したままにする。
3. SW1（RST）を押して離す。
4. SW2を離す。
5. STM32CubeProgrammerでUSB接続を選び、内蔵ROM DFUから書き込む。

通常起動ではBOOTを押さず、RSTだけを押します。USB更新が失敗してもJ7は残るため、ST-LINKを再接続して復旧できます。PA14はSWCLKとBOOT0を兼ねるため、接続しにくい場合はSTM32CubeProgrammerの「connect under reset」を使い、NRSTを接続した状態で復旧します。

## 6. 組立・機構・DNP

- PCBAのAssembly sideはTop sideです。
- J1〜J5のpin順は`SIGNAL / VBEC / GND`で、pin 1は四角パッドです。
- J5はESC信号出力とBEC入力を兼ねます。ヘッダー実装後も向きを識別できるようにしてください。
- J1〜J5はBOM上でDNPとし、PCBA後に手はんだします。JLCPCBの部品マッチングで勝手に代替ヘッダーを割り当てません。
- J7、SW1、SW2はTop-side PCBA実装です。J7のpin 1マーク、物理position 7の欠落、実装回転を部品プレビューで確認します。
- TP1〜TP8はTop-sideの裸パッドで、実装部品ではありません。
- H1/H2および固定穴はありません。USBケーブルやRCハーネスの引張力を基板だけに掛けず、筐体側でストレインリリーフします。
- B面中央の20 × 12 mmテープ領域には、B面部品、B面パッド、ビア、THT突起、B面シルクを置きません。
- 外形は配置・配線余裕を確保するため60 × 30 mmです。JLCPCB注文画面で工程辺、フィデューシャル、ツーリングホール、パネル条件、追加費用を確認します。

## 7. JLCPCB発注チェックリスト

2026-07-22のRev.1生成時点では、KiCad 10.0.4によるERC/DRC、未接続、回路図・PCB整合性、独立基板監査、JLCPCB BOM/CPL整合性がすべてPASSしています。最終結果は`fabrication/build/reports/build_manifest.txt`を参照してください。macOS版KiCad 10.0.4では、wxWidgets由来のCLI異常終了を避ける最小互換シムを同版だけに適用します。DRCエンジンと設計規則は変更しません。

この60 × 30 mm版は旧50 × 25 mm版とGerber、BOM、CPLが互換ではありません。旧注文が製造開始前ならJLCPCBへ停止／編集可否を確認し、3ファイルを同一ビルドの最終版へ全て差し替えます。すでに製造開始済みなら別注文として扱い、旧データと混在させません。

### 製造データ

1. ソースを含めて再現確認する場合は`./scripts/rebuild.sh`、最終KiCadファイルから製造出力だけを更新する場合は`./scripts/export.sh`を実行する。
2. ERC、DRC、未接続、回路図・PCB整合性の各検証が正常終了し、最終レポートにError/Warningや不一致が残っていないことを確認する。CLI DRCの異常終了やレポート欠落は合格とみなさず、KiCad GUIのDRCで再確認して結果を保存する。
3. Gerber ViewerでF.Cu、In1.Cu、In2.Cu、B.Cu、F/B Mask、F/B Silk、Edge.Cuts、PTH、NPTHを確認する。
4. Gerber ZIP、BOM CSV、CPL CSVをそれぞれ対応する注文欄へアップロードする。保管用のプロジェクト一式ZIPをGerber欄へ使用しない。
5. BOMとCPLの実装対象Referenceが一致し、DNPと非部品パッドが除外されていることを確認する。

### PCB注文

1. Layers: 4、Thickness: 1.0 mm、Material: FR-4を選ぶ。
2. Stack-upは`JLC3313`を選び、外層35 µm、内層15.2 µm、3313 prepreg 0.0994 mm × 2、NP-155F core 0.700 mmであることを注文プレビューで照合する。
3. Surface finishはENIGを選ぶ。
4. `USB_DIFF`の0.15 mm / 0.15 mmを90 Ω保証値とみなさず、JLCPCB公式計算機と注文時DFMの結果を確認する。
5. オンラインGerber Viewerで60 × 30 mm外形、USB-C端、固定穴が存在しないこと、B面テープ領域、ドリル、シルク極性を確認する。

### PCBA注文

1. PCB Assemblyを有効にし、Assembly sideをTop sideにする。
2. 各LCSC番号、メーカー型番、値、パッケージ、実装面をBOMと照合する。
3. U1〜U5、D1/D2、J6/J7、SW1/SW2、Q1〜Q4、C1のpin 1、回転、極性をプレビューで一つずつ確認する。
4. J1〜J5だけが実装対象から除外され、J7とSW1/SW2は実装対象に含まれ、TP1〜TP8とH1/H2は部品として現れないことを確認する。
5. 欠品時に自動代替を無条件で承認せず、電気的・機械的互換性を確認する。
6. U1が`STM32G0B1CET6` / `C5270267`、C1が`EEHZK1E101UP` / `C454668`であることを確認する。U2は`TMUX7236PWR` / `C37096021`の在庫を確保してから注文を確定する。

## 8. 初回通電と受入検査

1. 到着時に60 × 30 mm外形、固定穴がないこと、USB-C/J7/SW1/SW2位置、はんだブリッジ、部品ずれ、pin 1、D1/D2方向、C1極性を検査する。
2. 無通電でVBEC–GND、3V3–GND、USB VBUS–VBECの抵抗を測る。USB VBUSから+3V3にはD2/U3の意図した片方向経路があるため、導通音だけで短絡と判定せず、ダイオード極性と抵抗値を回路図に照合する。
3. ESCの代わりに電流制限付き電源を使い、J5 pin 2へ+6.0 V、pin 3へGNDを接続する。初期電流制限は約100 mAとし、TP1のVBECとTP2の+3V3、消費電流、発熱を確認する。
4. BECを切ってUSBだけを接続し、VBEC=0 V付近、`LOGIC_RAW`=VBUS−D2順方向電圧、+3V3=約3.3 Vを確認する。U2、サーボ、ESCが無給電であることも確認する。
5. USBを外してBECだけを接続し、USB VBUSが0 V付近のまま、`LOGIC_RAW`と+3V3が正常で、U5がVBEC上昇後にMUXを有効化することを確認する。
6. 初回はJ7とST-LINKで接続し、オプションバイトを読み戻して保存する。その後、BOOT+RST操作でMacからUSB DFU認識できることを確認する。
7. MCUをNRST Lowに保持し、外部PWM発生器でJ1→J4、J2→J5のMANUAL通過を確認する。
8. HSI48/CRSを設定したファームウェアでUSB CDC認識を確認する。
9. heartbeat停止、USB抜去、範囲外指令、RC信号抜去、VBEC低下、watchdog resetを個別に試験し、仕様どおり遷移することをオシロスコープで確認する。
10. 車両試験はタイヤを浮かせ、モーターが突然回転しても車体が移動しない状態から始める。

## 9. 発注可否の判定

次をすべて満たすまでは、Gerber/BOM/CPLが生成されていても「発注可能」とは扱いません。

- 最終のERC、DRC、未接続、回路図・PCB整合性の結果を確認できる。
- CLI DRCが異常終了した場合は、同じ最終基板に対するKiCad GUI DRCの結果と、CLI側の異常内容が記録されている。
- 発注画面で4層・1.0 mmの`JLC3313`とENIGが選択され、公式計算機および注文時DFMでUSB差動条件が再確認されている。
- U2を含む全PCBA部品の在庫、実装面、回転、極性がJLCPCBのプレビューで確認されている。
- USBだけで+3V3が正常に給電される一方、VBEC/U2/サーボ/ESCへ逆給電しないこと、BECだけでUSB VBUSへ逆流しないこと、3.3 V PWMをESC/サーボが認識すること、VBEC負荷時の電圧とD1/D2/U3温度が試作機で確認されている。
- 初回ST-LINK接続とオプションバイトの読み戻し、BOOT+RSTによるUSB DFU認識が実機で確認されている。

## 10. JLCPCB公式参考資料

- [Multi-Layer PCB Standard Laminated Structures](https://jlcpcb.com/help/article/multi-layer-pcb-standard-laminated-structures) — 標準積層表、完成銅厚、3313と旧2313の関係
- [User Guide to the JLCPCB Impedance Calculator](https://jlcpcb.com/help/article/user-guide-to-the-jlcpcb-impedance-calculator) — インピーダンス計算機の入力項目と材料条件
- [Multilayer PCB Stack-up and Layout Best Practices](https://jlcpcb.com/blog/multilayer-pcb-design-guidelines) — 多層積層、基準面、配線およびDFMのガイド
- [STM32G0x1 Reference Manual RM0444](https://www.st.com/resource/en/reference_manual/DM00371828-.pdf) — boot mode、`BOOT_LOCK`、`nBOOT1`、`nBOOT_SEL`、`nBOOT0`
- [AN2606 Introduction to system memory boot mode](https://www.st.com/resource/en/application_note/an2606-introduction-to-system-memory-boot-mode-on-stm32-mcus-stmicroelectronics.pdf) — STM32G0B1のSystem memory bootloaderとUSB DFU
