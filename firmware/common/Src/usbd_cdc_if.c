#include "usbd_cdc_if.h"

#include <string.h>

#include "jpbb_usb.h"
#include "usb_device.h"

#define APP_RX_DATA_SIZE 64U
#define APP_TX_DATA_SIZE 64U

static uint8_t user_rx_buffer[APP_RX_DATA_SIZE];
static uint8_t user_tx_buffer[APP_TX_DATA_SIZE];

static int8_t cdc_init(void) {
  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, user_tx_buffer, 0U);
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, user_rx_buffer);
  return (int8_t)USBD_OK;
}

static int8_t cdc_deinit(void) {
  return (int8_t)USBD_OK;
}

static int8_t cdc_control(uint8_t command, uint8_t *buffer, uint16_t length) {
  (void)command;
  (void)buffer;
  (void)length;
  return (int8_t)USBD_OK;
}

static int8_t cdc_receive(uint8_t *buffer, uint32_t *length) {
  jpbb_usb_receive_from_isr(buffer, *length);
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, user_rx_buffer);
  (void)USBD_CDC_ReceivePacket(&hUsbDeviceFS);
  return (int8_t)USBD_OK;
}

static int8_t cdc_transmit_complete(uint8_t *buffer, uint32_t *length,
                                    uint8_t endpoint) {
  (void)buffer;
  (void)length;
  (void)endpoint;
  return (int8_t)USBD_OK;
}

USBD_CDC_ItfTypeDef USBD_Interface_fops_FS = {
  cdc_init,
  cdc_deinit,
  cdc_control,
  cdc_receive,
  cdc_transmit_complete
};

uint8_t CDC_Transmit_FS(uint8_t *buffer, uint16_t length) {
  USBD_CDC_HandleTypeDef *cdc =
      (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;

  if (cdc == NULL || cdc->TxState != 0U) {
    return (uint8_t)USBD_BUSY;
  }
  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, buffer, length);
  return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}
