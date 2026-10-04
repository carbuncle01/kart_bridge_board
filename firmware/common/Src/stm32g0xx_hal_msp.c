#include "jpbb_board.h"

extern PCD_HandleTypeDef hpcd_USB_DRD_FS;

void HAL_MspInit(void) {
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  __HAL_RCC_PWR_CLK_ENABLE();
  HAL_NVIC_SetPriority(PendSV_IRQn, 3U, 0U);
}

void HAL_TIM_IC_MspInit(TIM_HandleTypeDef *timer) {
  GPIO_InitTypeDef gpio = {0};
  if (timer->Instance != TIM2) {
    return;
  }

  __HAL_RCC_TIM2_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_PULLUP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Alternate = GPIO_AF2_TIM2;
  HAL_GPIO_Init(GPIOA, &gpio);

  HAL_NVIC_SetPriority(TIM2_IRQn, 1U, 0U);
  HAL_NVIC_EnableIRQ(TIM2_IRQn);
}

void HAL_TIM_PWM_MspInit(TIM_HandleTypeDef *timer) {
  if (timer->Instance == TIM3) {
    __HAL_RCC_TIM3_CLK_ENABLE();
  }
}

void HAL_TIM_MspPostInit(TIM_HandleTypeDef *timer) {
  GPIO_InitTypeDef gpio = {0};
  if (timer->Instance != TIM3) {
    return;
  }

  __HAL_RCC_GPIOB_CLK_ENABLE();
  gpio.Pin = GPIO_PIN_4 | GPIO_PIN_5;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Alternate = GPIO_AF1_TIM3;
  HAL_GPIO_Init(GPIOB, &gpio);
}

void HAL_ADC_MspInit(ADC_HandleTypeDef *adc) {
  GPIO_InitTypeDef gpio = {0};
  if (adc->Instance != ADC1) {
    return;
  }

  __HAL_RCC_ADC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  gpio.Pin = GPIO_PIN_4;
  gpio.Mode = GPIO_MODE_ANALOG;
  gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &gpio);
}

void HAL_PCD_MspInit(PCD_HandleTypeDef *pcd) {
  if (pcd->Instance != USB_DRD_FS) {
    return;
  }

  __HAL_RCC_USB_CLK_ENABLE();
  HAL_NVIC_SetPriority(USB_UCPD1_2_IRQn, 0U, 0U);
  HAL_NVIC_EnableIRQ(USB_UCPD1_2_IRQn);
}
