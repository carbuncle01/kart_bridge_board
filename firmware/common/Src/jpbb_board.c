#include "jpbb_board.h"

#include <string.h>

#define SAFE_AUTO_PORT GPIOB
#define SAFE_AUTO_PIN GPIO_PIN_0
#define USB_PRESENT_PORT GPIOB
#define USB_PRESENT_PIN GPIO_PIN_1

#define RC_PORT GPIOA
#define RC_CH1_PIN GPIO_PIN_0
#define RC_CH2_PIN GPIO_PIN_1
#define RC_CH3_PIN GPIO_PIN_2

#define PWM_PORT GPIOB
#define PWM_SERVO_PIN GPIO_PIN_4
#define PWM_ESC_PIN GPIO_PIN_5

TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;
ADC_HandleTypeDef hadc1;
IWDG_HandleTypeDef hiwdg;

static volatile jpbb_rc_channel_t rc_channels[3];
static volatile uint32_t rc_low_start[3];
static uint16_t servo_pwm_us = JPBB_PWM_NEUTRAL_US;
static uint16_t esc_pwm_us = JPBB_PWM_NEUTRAL_US;
static bool pwm_started;
static bool watchdog_started;

void HAL_TIM_MspPostInit(TIM_HandleTypeDef *timer);

static void system_clock_config(void) {
  RCC_OscInitTypeDef osc = {0};
  RCC_ClkInitTypeDef clk = {0};
  RCC_PeriphCLKInitTypeDef peripheral = {0};
  RCC_CRSInitTypeDef crs = {0};

  osc.OscillatorType = RCC_OSCILLATORTYPE_HSI | RCC_OSCILLATORTYPE_HSI48;
  osc.HSIState = RCC_HSI_ON;
  osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  osc.HSI48State = RCC_HSI48_ON;
  osc.PLL.PLLState = RCC_PLL_ON;
  osc.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  osc.PLL.PLLM = RCC_PLLM_DIV1;
  osc.PLL.PLLN = 8;
  osc.PLL.PLLP = RCC_PLLP_DIV2;
  osc.PLL.PLLQ = RCC_PLLQ_DIV2;
  osc.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
    jpbb_error_handler();
  }

  clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                  RCC_CLOCKTYPE_PCLK1;
  clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clk.APB1CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2) != HAL_OK) {
    jpbb_error_handler();
  }

  peripheral.PeriphClockSelection = RCC_PERIPHCLK_USB;
  peripheral.UsbClockSelection = RCC_USBCLKSOURCE_HSI48;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral) != HAL_OK) {
    jpbb_error_handler();
  }

  __HAL_RCC_CRS_CLK_ENABLE();
  crs.Prescaler = RCC_CRS_SYNC_DIV1;
  crs.Source = RCC_CRS_SYNC_SOURCE_USB;
  crs.Polarity = RCC_CRS_SYNC_POLARITY_RISING;
  crs.ReloadValue = __HAL_RCC_CRS_RELOADVALUE_CALCULATE(HSI48_VALUE, 1000U);
  crs.ErrorLimitValue = RCC_CRS_ERRORLIMIT_DEFAULT;
  crs.HSI48CalibrationValue = RCC_CRS_HSI48CALIBRATION_DEFAULT;
  HAL_RCCEx_CRSConfig(&crs);
}

static void safe_gpio_init(void) {
  GPIO_InitTypeDef gpio = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_PWR_CLK_ENABLE();

#if defined(PWR_CR2_USV)
  SET_BIT(PWR->CR2, PWR_CR2_USV);
#endif

  HAL_GPIO_WritePin(SAFE_AUTO_PORT, SAFE_AUTO_PIN, GPIO_PIN_RESET);
  gpio.Pin = SAFE_AUTO_PIN;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(SAFE_AUTO_PORT, &gpio);

  gpio.Pin = USB_PRESENT_PIN;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(USB_PRESENT_PORT, &gpio);
}

void jpbb_board_init(void) {
  HAL_Init();
  system_clock_config();
  safe_gpio_init();
  jpbb_manual_force();
}

uint32_t jpbb_millis(void) {
  return HAL_GetTick();
}

void jpbb_manual_force(void) {
  HAL_GPIO_WritePin(SAFE_AUTO_PORT, SAFE_AUTO_PIN, GPIO_PIN_RESET);
}

bool jpbb_auto_select(bool enable) {
  if (!enable) {
    jpbb_manual_force();
    return true;
  }
  /*
   * Q1/Q2で入力は反転されているため、PA0/PA1がHighのとき
   * TMUXへ直接入るMANUAL信号はLowです。AUTO PWMもLowの期間だけ
   * SELを変更し、切り替え途中の短いパルスを避けます。
   */
  const bool manual_inputs_low =
      HAL_GPIO_ReadPin(RC_PORT, RC_CH1_PIN) == GPIO_PIN_SET &&
      HAL_GPIO_ReadPin(RC_PORT, RC_CH2_PIN) == GPIO_PIN_SET;
  if (!pwm_started || !jpbb_pwm_frame_boundary() || !manual_inputs_low) {
    return false;
  }
  HAL_GPIO_WritePin(SAFE_AUTO_PORT, SAFE_AUTO_PIN, GPIO_PIN_SET);
  return true;
}

bool jpbb_auto_is_selected(void) {
  return HAL_GPIO_ReadPin(SAFE_AUTO_PORT, SAFE_AUTO_PIN) == GPIO_PIN_SET;
}

void jpbb_rc_init(void) {
  TIM_IC_InitTypeDef capture = {0};
  TIM_MasterConfigTypeDef master = {0};

  memset((void *)rc_channels, 0, sizeof(rc_channels));
  memset((void *)rc_low_start, 0, sizeof(rc_low_start));

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = (uint32_t)(SystemCoreClock / 1000000U) - 1U;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 0xFFFFFFFFU;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_IC_Init(&htim2) != HAL_OK) {
    jpbb_error_handler();
  }

  master.MasterOutputTrigger = TIM_TRGO_RESET;
  master.MasterOutputTrigger2 = TIM_TRGO2_RESET;
  master.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &master) != HAL_OK) {
    jpbb_error_handler();
  }

  capture.ICPolarity = TIM_INPUTCHANNELPOLARITY_BOTHEDGE;
  capture.ICSelection = TIM_ICSELECTION_DIRECTTI;
  capture.ICPrescaler = TIM_ICPSC_DIV1;
  capture.ICFilter = 4U;
  if (HAL_TIM_IC_ConfigChannel(&htim2, &capture, TIM_CHANNEL_1) != HAL_OK ||
      HAL_TIM_IC_ConfigChannel(&htim2, &capture, TIM_CHANNEL_2) != HAL_OK ||
      HAL_TIM_IC_ConfigChannel(&htim2, &capture, TIM_CHANNEL_3) != HAL_OK) {
    jpbb_error_handler();
  }

  if (HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_1) != HAL_OK ||
      HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_2) != HAL_OK ||
      HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_3) != HAL_OK) {
    jpbb_error_handler();
  }
}

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *timer) {
  size_t index;
  uint32_t channel;
  uint16_t pin;

  if (timer->Instance != TIM2) {
    return;
  }

  if (timer->Channel == HAL_TIM_ACTIVE_CHANNEL_1) {
    index = 0U;
    channel = TIM_CHANNEL_1;
    pin = RC_CH1_PIN;
  } else if (timer->Channel == HAL_TIM_ACTIVE_CHANNEL_2) {
    index = 1U;
    channel = TIM_CHANNEL_2;
    pin = RC_CH2_PIN;
  } else if (timer->Channel == HAL_TIM_ACTIVE_CHANNEL_3) {
    index = 2U;
    channel = TIM_CHANNEL_3;
    pin = RC_CH3_PIN;
  } else {
    return;
  }

  const uint32_t captured = HAL_TIM_ReadCapturedValue(timer, channel);
  const GPIO_PinState level = HAL_GPIO_ReadPin(RC_PORT, pin);

  /*
   * Q1-Q3 invert the receiver signal.  A low MCU input marks the beginning
   * of the receiver's positive pulse; the following high level ends it.
   */
  if (level == GPIO_PIN_RESET) {
    rc_low_start[index] = captured;
    return;
  }

  const uint32_t width = captured - rc_low_start[index];
  if (width >= JPBB_RC_VALID_MIN_US && width <= JPBB_RC_VALID_MAX_US) {
    rc_channels[index].pulse_us = (uint16_t)width;
    rc_channels[index].last_update_ms = HAL_GetTick();
    rc_channels[index].valid = true;
  } else {
    rc_channels[index].valid = false;
  }
}

void jpbb_rc_poll(void) {
  const uint32_t now = HAL_GetTick();
  for (size_t i = 0U; i < 3U; ++i) {
    if (rc_channels[i].valid &&
        (now - rc_channels[i].last_update_ms) > JPBB_RC_TIMEOUT_MS) {
      rc_channels[i].valid = false;
    }
  }
}

jpbb_rc_channel_t jpbb_rc_get(size_t index) {
  jpbb_rc_channel_t value = {0};
  if (index >= 3U) {
    return value;
  }

  __disable_irq();
  value = rc_channels[index];
  __enable_irq();
  return value;
}

bool jpbb_rc_all_valid(void) {
  return rc_channels[0].valid && rc_channels[1].valid &&
         rc_channels[2].valid;
}

void jpbb_pwm_init(void) {
  TIM_OC_InitTypeDef output = {0};
  TIM_MasterConfigTypeDef master = {0};

  htim3.Instance = TIM3;
  htim3.Init.Prescaler = (uint32_t)(SystemCoreClock / 1000000U) - 1U;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = JPBB_PWM_FRAME_US - 1U;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_PWM_Init(&htim3) != HAL_OK) {
    jpbb_error_handler();
  }

  master.MasterOutputTrigger = TIM_TRGO_RESET;
  master.MasterOutputTrigger2 = TIM_TRGO2_RESET;
  master.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &master) != HAL_OK) {
    jpbb_error_handler();
  }

  output.OCMode = TIM_OCMODE_PWM1;
  output.Pulse = JPBB_PWM_NEUTRAL_US;
  output.OCPolarity = TIM_OCPOLARITY_HIGH;
  output.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &output, TIM_CHANNEL_1) != HAL_OK ||
      HAL_TIM_PWM_ConfigChannel(&htim3, &output, TIM_CHANNEL_2) != HAL_OK) {
    jpbb_error_handler();
  }

  HAL_TIM_MspPostInit(&htim3);
  if (HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1) != HAL_OK ||
      HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2) != HAL_OK) {
    jpbb_error_handler();
  }
  pwm_started = true;
}

static uint16_t clamp_pwm(uint16_t value) {
  if (value < JPBB_PWM_MIN_US) {
    return JPBB_PWM_MIN_US;
  }
  if (value > JPBB_PWM_MAX_US) {
    return JPBB_PWM_MAX_US;
  }
  return value;
}

void jpbb_pwm_set(uint16_t servo_us, uint16_t esc_us) {
  servo_pwm_us = clamp_pwm(servo_us);
  esc_pwm_us = clamp_pwm(esc_us);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, servo_pwm_us);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, esc_pwm_us);
}

void jpbb_pwm_get(uint16_t *servo_us, uint16_t *esc_us) {
  if (servo_us != NULL) {
    *servo_us = servo_pwm_us;
  }
  if (esc_us != NULL) {
    *esc_us = esc_pwm_us;
  }
}

bool jpbb_pwm_frame_boundary(void) {
  if (!pwm_started) {
    return false;
  }
  const uint32_t counter = __HAL_TIM_GET_COUNTER(&htim3);
  const uint32_t latest_falling_edge =
      (servo_pwm_us > esc_pwm_us) ? servo_pwm_us : esc_pwm_us;
  return counter > (latest_falling_edge + 200U) &&
         counter < (JPBB_PWM_FRAME_US - 200U);
}

void jpbb_adc_init(void) {
  ADC_ChannelConfTypeDef channel = {0};

  hadc1.Instance = ADC1;
  hadc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
  hadc1.Init.Resolution = ADC_RESOLUTION_12B;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc1.Init.LowPowerAutoWait = DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.NbrOfConversion = 1;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
  hadc1.Init.DMAContinuousRequests = DISABLE;
  hadc1.Init.Overrun = ADC_OVR_DATA_PRESERVED;
  hadc1.Init.SamplingTimeCommon1 = ADC_SAMPLETIME_160CYCLES_5;
  hadc1.Init.SamplingTimeCommon2 = ADC_SAMPLETIME_160CYCLES_5;
  hadc1.Init.OversamplingMode = DISABLE;
  hadc1.Init.TriggerFrequencyMode = ADC_TRIGGER_FREQ_HIGH;
  if (HAL_ADC_Init(&hadc1) != HAL_OK) {
    jpbb_error_handler();
  }

  channel.Channel = ADC_CHANNEL_4;
  channel.Rank = ADC_REGULAR_RANK_1;
  channel.SamplingTime = ADC_SAMPLINGTIME_COMMON_1;
  if (HAL_ADC_ConfigChannel(&hadc1, &channel) != HAL_OK) {
    jpbb_error_handler();
  }

  if (HAL_ADCEx_Calibration_Start(&hadc1) != HAL_OK) {
    jpbb_error_handler();
  }
}

uint16_t jpbb_vbec_read_mv(void) {
  uint32_t raw;
  uint32_t sense_mv;
  uint32_t vbec_mv;

  if (HAL_ADC_Start(&hadc1) != HAL_OK ||
      HAL_ADC_PollForConversion(&hadc1, 10U) != HAL_OK) {
    return 0U;
  }
  raw = HAL_ADC_GetValue(&hadc1);
  (void)HAL_ADC_Stop(&hadc1);

  sense_mv = (raw * 3300U + 2047U) / 4095U;
  vbec_mv = (sense_mv * 122U + 11U) / 22U;
  return (vbec_mv > UINT16_MAX) ? UINT16_MAX : (uint16_t)vbec_mv;
}

bool jpbb_vbec_is_healthy(uint16_t mv) {
  return mv >= 5200U && mv <= 8500U;
}

bool jpbb_usb_vbus_present(void) {
  return HAL_GPIO_ReadPin(USB_PRESENT_PORT, USB_PRESENT_PIN) == GPIO_PIN_RESET;
}

void jpbb_watchdog_init(void) {
  hiwdg.Instance = IWDG;
  hiwdg.Init.Prescaler = IWDG_PRESCALER_64;
  hiwdg.Init.Window = IWDG_WINDOW_DISABLE;
  hiwdg.Init.Reload = 500U;
  if (HAL_IWDG_Init(&hiwdg) != HAL_OK) {
    jpbb_error_handler();
  }
  watchdog_started = true;
}

void jpbb_watchdog_refresh(void) {
  if (watchdog_started) {
    (void)HAL_IWDG_Refresh(&hiwdg);
  }
}

void jpbb_status_snapshot(jpbb_status_t *status) {
  if (status == NULL) {
    return;
  }
  for (size_t i = 0U; i < 3U; ++i) {
    status->channel[i] = jpbb_rc_get(i);
  }
  status->vbec_mv = jpbb_vbec_read_mv();
  status->usb_present = jpbb_usb_vbus_present();
  status->auto_selected = jpbb_auto_is_selected();
}

void jpbb_error_handler(void) {
  __disable_irq();
  jpbb_manual_force();
  while (true) {
  }
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line) {
  (void)file;
  (void)line;
  jpbb_error_handler();
}
#endif
