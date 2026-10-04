#include "jpbb_board.h"

extern PCD_HandleTypeDef hpcd_USB_DRD_FS;

void NMI_Handler(void) {
}

void HardFault_Handler(void) {
  jpbb_error_handler();
}

void SVC_Handler(void) {
}

void PendSV_Handler(void) {
}

void SysTick_Handler(void) {
  HAL_IncTick();
}

void TIM2_IRQHandler(void) {
  HAL_TIM_IRQHandler(&htim2);
}

void USB_UCPD1_2_IRQHandler(void) {
  HAL_PCD_IRQHandler(&hpcd_USB_DRD_FS);
}
