#ifndef JPBB_BOARD_H
#define JPBB_BOARD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "stm32g0xx_hal.h"

#define JPBB_PWM_MIN_US 1000U
#define JPBB_PWM_NEUTRAL_US 1500U
#define JPBB_SERVO_SAFE_US 1500U
#define JPBB_ESC_SAFE_US 1500U
#define JPBB_PWM_MAX_US 2000U
#define JPBB_PWM_FRAME_US 20000U
#define JPBB_RC_VALID_MIN_US 850U
#define JPBB_RC_VALID_MAX_US 2150U
#define JPBB_RC_TIMEOUT_MS 100U

typedef struct {
  uint16_t pulse_us;
  uint32_t last_update_ms;
  bool valid;
} jpbb_rc_channel_t;

typedef struct {
  jpbb_rc_channel_t channel[3];
  uint16_t vbec_mv;
  bool usb_present;
  bool auto_selected;
} jpbb_status_t;

extern TIM_HandleTypeDef htim2;
extern TIM_HandleTypeDef htim3;
extern ADC_HandleTypeDef hadc1;
extern IWDG_HandleTypeDef hiwdg;

void jpbb_board_init(void);
void jpbb_error_handler(void);
uint32_t jpbb_millis(void);

void jpbb_manual_force(void);
bool jpbb_auto_select(bool enable);
bool jpbb_auto_is_selected(void);

void jpbb_rc_init(void);
void jpbb_rc_poll(void);
jpbb_rc_channel_t jpbb_rc_get(size_t index);
bool jpbb_rc_all_valid(void);

void jpbb_pwm_init(void);
void jpbb_pwm_set(uint16_t servo_us, uint16_t esc_us);
void jpbb_pwm_get(uint16_t *servo_us, uint16_t *esc_us);
bool jpbb_pwm_frame_boundary(void);

void jpbb_adc_init(void);
uint16_t jpbb_vbec_read_mv(void);
bool jpbb_vbec_is_healthy(uint16_t mv);

bool jpbb_usb_vbus_present(void);
void jpbb_watchdog_init(void);
void jpbb_watchdog_refresh(void);
void jpbb_status_snapshot(jpbb_status_t *status);

#endif
