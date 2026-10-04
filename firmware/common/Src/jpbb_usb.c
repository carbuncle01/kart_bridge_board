#include "jpbb_usb.h"

#include <string.h>

#include "usb_device.h"
#include "usbd_cdc_if.h"

#define RX_RING_SIZE 512U

static volatile uint8_t rx_ring[RX_RING_SIZE];
static volatile uint16_t rx_head;
static volatile uint16_t rx_tail;

void jpbb_usb_init(void) {
  rx_head = 0U;
  rx_tail = 0U;
  MX_USB_DEVICE_Init();
}

void jpbb_usb_poll(void) {
  /* The ST USB device stack is interrupt driven. */
}

bool jpbb_usb_is_configured(void) {
  return hUsbDeviceFS.dev_state == USBD_STATE_CONFIGURED;
}

void jpbb_usb_receive_from_isr(const uint8_t *data, uint32_t length) {
  for (uint32_t i = 0U; i < length; ++i) {
    const uint16_t next = (uint16_t)((rx_head + 1U) % RX_RING_SIZE);
    if (next == rx_tail) {
      break;
    }
    rx_ring[rx_head] = data[i];
    rx_head = next;
  }
}

bool jpbb_usb_read_line(char *buffer, size_t capacity) {
  size_t output = 0U;
  uint16_t cursor = rx_tail;
  bool found = false;

  if (buffer == NULL || capacity < 2U) {
    return false;
  }

  while (cursor != rx_head) {
    const char ch = (char)rx_ring[cursor];
    cursor = (uint16_t)((cursor + 1U) % RX_RING_SIZE);
    if (ch == '\n' || ch == '\r') {
      found = output > 0U;
      if (found) {
        break;
      }
      rx_tail = cursor;
      continue;
    }
    if (output + 1U < capacity) {
      buffer[output++] = ch;
    }
  }

  if (!found) {
    return false;
  }

  buffer[output] = '\0';
  rx_tail = cursor;
  while (rx_tail != rx_head) {
    const char ch = (char)rx_ring[rx_tail];
    if (ch != '\n' && ch != '\r') {
      break;
    }
    rx_tail = (uint16_t)((rx_tail + 1U) % RX_RING_SIZE);
  }
  return true;
}

bool jpbb_usb_write_bytes(const uint8_t *data, uint16_t length) {
  if (!jpbb_usb_is_configured() || data == NULL || length == 0U) {
    return false;
  }
  return CDC_Transmit_FS((uint8_t *)data, length) == USBD_OK;
}

bool jpbb_usb_write(const char *text) {
  if (text == NULL) {
    return false;
  }
  const size_t length = strlen(text);
  if (length == 0U || length > UINT16_MAX) {
    return false;
  }
  return jpbb_usb_write_bytes((const uint8_t *)text, (uint16_t)length);
}
