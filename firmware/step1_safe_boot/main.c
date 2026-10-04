#include "jpbb_board.h"

/*
 * Debuggerでこの値が増え続けることを確認できます。
 * PB4（MCU_SERVO_PWM_GPIO）も1秒ごとに1400/1600 usへ変化しますが、
 * SAFE_AUTO_SELは常にLowなのでJ4/J5には出力されません。
 */
volatile uint32_t jpbb_step1_heartbeat;

int main(void) {
  uint32_t previous = 0U;
  bool alternate = false;

  jpbb_board_init();
  jpbb_manual_force();
  jpbb_pwm_init();
  jpbb_pwm_set(JPBB_PWM_NEUTRAL_US, JPBB_PWM_NEUTRAL_US);

  while (1) {
    const uint32_t now = jpbb_millis();
    if ((now - previous) >= 1000U) {
      previous = now;
      ++jpbb_step1_heartbeat;
      alternate = !alternate;
      jpbb_pwm_set(alternate ? 1600U : 1400U, JPBB_PWM_NEUTRAL_US);
    }
    jpbb_manual_force();
  }
}
