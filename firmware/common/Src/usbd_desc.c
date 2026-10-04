#include "usbd_desc.h"

#include "stm32g0xx_hal.h"
#include "usbd_core.h"

#define JPBB_USB_VID 0x0483U
#define JPBB_USB_PID 0x5740U
#define JPBB_USB_LANGID 0x0409U
#define JPBB_USB_MANUFACTURER "Kart prototype"
#define JPBB_USB_PRODUCT "Kart Bridge Board"
#define JPBB_USB_CONFIGURATION "CDC configuration"
#define JPBB_USB_INTERFACE "Kart command port"

#define USB_LEN_DEV_DESC 18U
#define USB_LEN_LANGID_STR_DESC 4U
#define USB_MAX_EP0_SIZE 64U

static uint8_t device_descriptor[USB_LEN_DEV_DESC] = {
  0x12U,
  USB_DESC_TYPE_DEVICE,
  0x00U, 0x02U,
  0x02U,
  0x02U,
  0x00U,
  USB_MAX_EP0_SIZE,
  LOBYTE(JPBB_USB_VID), HIBYTE(JPBB_USB_VID),
  LOBYTE(JPBB_USB_PID), HIBYTE(JPBB_USB_PID),
  0x00U, 0x01U,
  USBD_IDX_MFC_STR,
  USBD_IDX_PRODUCT_STR,
  USBD_IDX_SERIAL_STR,
  USBD_MAX_NUM_CONFIGURATION
};

static uint8_t lang_id_descriptor[USB_LEN_LANGID_STR_DESC] = {
  USB_LEN_LANGID_STR_DESC,
  USB_DESC_TYPE_STRING,
  LOBYTE(JPBB_USB_LANGID),
  HIBYTE(JPBB_USB_LANGID)
};

static uint8_t string_descriptor[USBD_MAX_STR_DESC_SIZ];
static uint8_t serial_string[26U];

static uint8_t *get_device_descriptor(USBD_SpeedTypeDef speed,
                                      uint16_t *length) {
  (void)speed;
  *length = sizeof(device_descriptor);
  return device_descriptor;
}

static uint8_t *get_lang_id_descriptor(USBD_SpeedTypeDef speed,
                                       uint16_t *length) {
  (void)speed;
  *length = sizeof(lang_id_descriptor);
  return lang_id_descriptor;
}

static uint8_t *make_string(const char *text, uint16_t *length) {
  USBD_GetString((uint8_t *)text, string_descriptor, length);
  return string_descriptor;
}

static uint8_t *get_manufacturer_string(USBD_SpeedTypeDef speed,
                                        uint16_t *length) {
  (void)speed;
  return make_string(JPBB_USB_MANUFACTURER, length);
}

static uint8_t *get_product_string(USBD_SpeedTypeDef speed,
                                   uint16_t *length) {
  (void)speed;
  return make_string(JPBB_USB_PRODUCT, length);
}

static void int_to_unicode(uint32_t value, uint8_t *buffer, uint8_t digits) {
  for (uint8_t i = 0U; i < digits; ++i) {
    const uint8_t nibble = (uint8_t)((value >> 28) & 0xFU);
    buffer[2U * i] =
        (nibble < 10U) ? (uint8_t)('0' + nibble)
                       : (uint8_t)('A' + nibble - 10U);
    buffer[2U * i + 1U] = 0U;
    value <<= 4;
  }
}

static uint8_t *get_serial_string(USBD_SpeedTypeDef speed,
                                  uint16_t *length) {
  (void)speed;
  const uint32_t uid0 = HAL_GetUIDw0();
  const uint32_t uid1 = HAL_GetUIDw1();
  const uint32_t uid2 = HAL_GetUIDw2();
  const uint32_t sum = uid0 + uid2;

  serial_string[0] = sizeof(serial_string);
  serial_string[1] = USB_DESC_TYPE_STRING;
  int_to_unicode(sum, &serial_string[2], 8U);
  int_to_unicode(uid1, &serial_string[18], 4U);
  *length = sizeof(serial_string);
  return serial_string;
}

static uint8_t *get_configuration_string(USBD_SpeedTypeDef speed,
                                         uint16_t *length) {
  (void)speed;
  return make_string(JPBB_USB_CONFIGURATION, length);
}

static uint8_t *get_interface_string(USBD_SpeedTypeDef speed,
                                     uint16_t *length) {
  (void)speed;
  return make_string(JPBB_USB_INTERFACE, length);
}

USBD_DescriptorsTypeDef FS_Desc = {
  get_device_descriptor,
  get_lang_id_descriptor,
  get_manufacturer_string,
  get_product_string,
  get_serial_string,
  get_configuration_string,
  get_interface_string
};
