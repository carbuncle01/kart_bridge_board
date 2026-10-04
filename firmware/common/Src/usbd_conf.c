#include "usbd_conf.h"

#include "usbd_core.h"

PCD_HandleTypeDef hpcd_USB_DRD_FS;

void *jpbb_usbd_malloc(uint32_t size) {
  static union {
    uint32_t alignment;
    uint8_t bytes[1024U];
  } pool;

  if (size > sizeof(pool.bytes)) {
    return NULL;
  }
  memset(pool.bytes, 0, sizeof(pool.bytes));
  return pool.bytes;
}

void jpbb_usbd_free(void *pointer) {
  (void)pointer;
}

void HAL_PCD_SetupStageCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_SetupStage((USBD_HandleTypeDef *)pcd->pData,
                     (uint8_t *)pcd->Setup);
}

void HAL_PCD_DataOutStageCallback(PCD_HandleTypeDef *pcd, uint8_t endpoint) {
  USBD_LL_DataOutStage((USBD_HandleTypeDef *)pcd->pData, endpoint,
                       pcd->OUT_ep[endpoint].xfer_buff);
}

void HAL_PCD_DataInStageCallback(PCD_HandleTypeDef *pcd, uint8_t endpoint) {
  USBD_LL_DataInStage((USBD_HandleTypeDef *)pcd->pData, endpoint,
                      pcd->IN_ep[endpoint].xfer_buff);
}

void HAL_PCD_SOFCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_SOF((USBD_HandleTypeDef *)pcd->pData);
}

void HAL_PCD_ResetCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_SetSpeed((USBD_HandleTypeDef *)pcd->pData, USBD_SPEED_FULL);
  USBD_LL_Reset((USBD_HandleTypeDef *)pcd->pData);
}

void HAL_PCD_SuspendCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_Suspend((USBD_HandleTypeDef *)pcd->pData);
}

void HAL_PCD_ResumeCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_Resume((USBD_HandleTypeDef *)pcd->pData);
}

void HAL_PCD_ISOOUTIncompleteCallback(PCD_HandleTypeDef *pcd,
                                      uint8_t endpoint) {
  USBD_LL_IsoOUTIncomplete((USBD_HandleTypeDef *)pcd->pData, endpoint);
}

void HAL_PCD_ISOINIncompleteCallback(PCD_HandleTypeDef *pcd,
                                     uint8_t endpoint) {
  USBD_LL_IsoINIncomplete((USBD_HandleTypeDef *)pcd->pData, endpoint);
}

void HAL_PCD_ConnectCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_DevConnected((USBD_HandleTypeDef *)pcd->pData);
}

void HAL_PCD_DisconnectCallback(PCD_HandleTypeDef *pcd) {
  USBD_LL_DevDisconnected((USBD_HandleTypeDef *)pcd->pData);
}

USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *device) {
  hpcd_USB_DRD_FS.Instance = USB_DRD_FS;
  hpcd_USB_DRD_FS.Init.dev_endpoints = 8U;
  hpcd_USB_DRD_FS.Init.speed = PCD_SPEED_FULL;
  hpcd_USB_DRD_FS.Init.phy_itface = PCD_PHY_EMBEDDED;
  hpcd_USB_DRD_FS.Init.Sof_enable = DISABLE;
  hpcd_USB_DRD_FS.Init.low_power_enable = DISABLE;
  hpcd_USB_DRD_FS.Init.lpm_enable = DISABLE;
  hpcd_USB_DRD_FS.Init.battery_charging_enable = DISABLE;

  hpcd_USB_DRD_FS.pData = device;
  device->pData = &hpcd_USB_DRD_FS;
  if (HAL_PCD_Init(&hpcd_USB_DRD_FS) != HAL_OK) {
    return USBD_FAIL;
  }

  (void)HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x00U, PCD_SNG_BUF, 0x40U);
  (void)HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x80U, PCD_SNG_BUF, 0x80U);
  (void)HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x01U, PCD_SNG_BUF, 0xC0U);
  (void)HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x81U, PCD_SNG_BUF, 0x100U);
  (void)HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x82U, PCD_SNG_BUF, 0x140U);
  return USBD_OK;
}

USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef *device) {
  (void)device;
  return (HAL_PCD_DeInit(&hpcd_USB_DRD_FS) == HAL_OK) ? USBD_OK : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *device) {
  (void)device;
  return (HAL_PCD_Start(&hpcd_USB_DRD_FS) == HAL_OK) ? USBD_OK : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *device) {
  (void)device;
  return (HAL_PCD_Stop(&hpcd_USB_DRD_FS) == HAL_OK) ? USBD_OK : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *device, uint8_t address,
                                  uint8_t type, uint16_t packet_size) {
  (void)device;
  return (HAL_PCD_EP_Open(&hpcd_USB_DRD_FS, address, packet_size, type) == HAL_OK)
             ? USBD_OK
             : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *device,
                                   uint8_t address) {
  (void)device;
  return (HAL_PCD_EP_Close(&hpcd_USB_DRD_FS, address) == HAL_OK) ? USBD_OK
                                                                : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *device,
                                   uint8_t address) {
  (void)device;
  return (HAL_PCD_EP_Flush(&hpcd_USB_DRD_FS, address) == HAL_OK) ? USBD_OK
                                                                : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *device,
                                   uint8_t address) {
  (void)device;
  return (HAL_PCD_EP_SetStall(&hpcd_USB_DRD_FS, address) == HAL_OK) ? USBD_OK
                                                                   : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef *device,
                                        uint8_t address) {
  (void)device;
  return (HAL_PCD_EP_ClrStall(&hpcd_USB_DRD_FS, address) == HAL_OK) ? USBD_OK
                                                                   : USBD_FAIL;
}

uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef *device, uint8_t address) {
  (void)device;
  if ((address & 0x80U) == 0x80U) {
    return hpcd_USB_DRD_FS.IN_ep[address & 0x7FU].is_stall;
  }
  return hpcd_USB_DRD_FS.OUT_ep[address & 0x7FU].is_stall;
}

USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef *device,
                                         uint8_t address) {
  (void)device;
  return (HAL_PCD_SetAddress(&hpcd_USB_DRD_FS, address) == HAL_OK) ? USBD_OK
                                                                 : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *device,
                                    uint8_t address, uint8_t *buffer,
                                    uint32_t length) {
  (void)device;
  return (HAL_PCD_EP_Transmit(&hpcd_USB_DRD_FS, address, buffer, length) ==
          HAL_OK)
             ? USBD_OK
             : USBD_FAIL;
}

USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *device,
                                          uint8_t address, uint8_t *buffer,
                                          uint32_t length) {
  (void)device;
  return (HAL_PCD_EP_Receive(&hpcd_USB_DRD_FS, address, buffer, length) ==
          HAL_OK)
             ? USBD_OK
             : USBD_FAIL;
}

uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *device, uint8_t address) {
  (void)device;
  return HAL_PCD_EP_GetRxCount(&hpcd_USB_DRD_FS, address);
}

void USBD_LL_Delay(uint32_t delay) {
  HAL_Delay(delay);
}
