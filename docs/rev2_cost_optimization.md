# JPBB-HW-DEF-002 — Rev.2低価格化方針

Rev.1はGitタグ`JPBB-01-Rev.1`で固定し、Rev.2は`rev2-cost-optimized`ブランチで管理する。

## Rev.2で変更する項目

| 項目 | Rev.1 | Rev.2 |
| --- | --- | --- |
| ビア | 最小0.20 mm穴 | 全て0.30 mm穴以上 |
| MCU | STM32G0B1CET6 / C5270267 | STM32G0B1CBT6 / C2847904（128 KiB） |
| 積層 | JLC3313指定 | JLCPCB標準4層、指定なし |
| USBインピーダンス | 製造保証あり | 指定なし。短いUSB Full-Speed配線として使用 |
| 表面処理 | ENIG | Lead-free HASL |
| 材料 | NP-155F指定 | 標準FR-4 TG135 |

基板外形60 × 30 mm、4層、1.0 mm、連続In1 GND、VBEC配線、USB保護、電源OR、RESET/BOOT、SWD、MANUAL既定、フェイルセーフ回路は維持する。J1〜J5は引き続きDNP。

U1のフラッシュ容量は128 KiBになるため、ファームウェアのリンク結果が余裕を含め128 KiB以内であることを発注・書き込み前に確認する。

## JLCPCB注文値

- 4 Layers / 1.0 mm / Green / White
- Material: 標準FR-4 TG135
- Surface Finish: LeadFree HASL
- Specify Layer Sequence: No
- Specify Stackup: No
- Impedance Control: No requirement
- Via Covering: PluggedまたはJLCPCB標準のtented相当
- Min via hole size/diameter: 0.30 mm
- Confirm Production File: No（必要ならYes）
- PCBA: Standard / Top Side / 2枚
- Edge Rails/Fiducials: Added by JLCPCB
- Depanel boards before delivery: No（自分で外す場合）

## 費用目標

前回見積りはPCB ¥16,050＋PCBA ¥18,704＝¥34,754（送料・税別）。高額要因だったインピーダンス管理、4線Kelvin試験、0.20 mmビア、ENIG、指定材料を外し、U1も低価格品へ変更する。注文時の在庫・為替に依存するが、同じPCB 5枚／PCBA 2枚で概ね¥18,000〜¥22,000を目標とする。

U2 TMUX7236は高価だが安全経路の中心なので、Rev.2初版では維持する。CD4053系への置換は、6 V系ロジック閾値、起動時MANUAL、無給電時の逆流、切替グリッチを試作確認できる別リビジョンで扱う。

10 kΩ（C25744）が注文時に不足した場合は、24個すべてを同じ0402・10 kΩ・±1%・50 V以上の在庫品へ置換できる。候補例はC2889342だが、在庫は注文画面で再確認し、異なる抵抗値を選ばない。
