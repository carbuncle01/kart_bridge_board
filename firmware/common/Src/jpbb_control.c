#include "jpbb_control.h"

#include <stddef.h>
#include <string.h>

static bool elapsed_at_least(uint32_t now, uint32_t then,
                             uint32_t interval) {
  return (now - then) >= interval;
}

static bool rc_present(const jpbb_control_inputs_t *inputs) {
  return inputs->rc1_valid || inputs->rc2_valid || inputs->rc3_valid;
}

static uint32_t confirm_time(jpbb_ch3_request_t request) {
  if (request == JPBB_CH3_REQUEST_RC) {
    return JPBB_CH3_RC_CONFIRM_MS;
  }
  if (request == JPBB_CH3_REQUEST_PC) {
    return JPBB_CH3_PC_CONFIRM_MS;
  }
  return JPBB_CH3_LOSS_CONFIRM_MS;
}

static void update_ch3(jpbb_control_t *control,
                       const jpbb_control_inputs_t *inputs) {
  jpbb_ch3_request_t observed;

  if (!inputs->rc3_valid) {
    observed = JPBB_CH3_UNKNOWN;
  } else if (inputs->ch3_us <= JPBB_CH3_RC_MAX_US) {
    observed = JPBB_CH3_REQUEST_RC;
  } else if (inputs->ch3_us >= JPBB_CH3_PC_MIN_US) {
    observed = JPBB_CH3_REQUEST_PC;
  } else {
    /* A two-position switch must not remain indefinitely between positions. */
    observed = JPBB_CH3_UNKNOWN;
  }

  if (observed == control->ch3_request) {
    control->ch3_candidate = observed;
    control->ch3_candidate_since_ms = inputs->now_ms;
    return;
  }

  if (observed != control->ch3_candidate) {
    control->ch3_candidate = observed;
    control->ch3_candidate_since_ms = inputs->now_ms;
    return;
  }

  if (elapsed_at_least(inputs->now_ms, control->ch3_candidate_since_ms,
                       confirm_time(observed))) {
    control->ch3_request = observed;
    control->ch3_candidate_since_ms = inputs->now_ms;
  }
}

void jpbb_control_init(jpbb_control_t *control) {
  if (control == NULL) {
    return;
  }
  memset(control, 0, sizeof(*control));
}

void jpbb_control_note_command(jpbb_control_t *control, uint32_t now_ms) {
  if (control == NULL) {
    return;
  }
  control->command_received = true;
  control->last_command_ms = now_ms;
}

void jpbb_control_note_heartbeat(jpbb_control_t *control, uint32_t now_ms) {
  if (control == NULL) {
    return;
  }
  control->heartbeat_received = true;
  control->last_heartbeat_ms = now_ms;
}

bool jpbb_control_arm_pc(jpbb_control_t *control,
                         const jpbb_control_inputs_t *inputs) {
  bool pc_permitted;

  if (control == NULL || inputs == NULL || !control->command_received ||
      !inputs->vbec_healthy || !inputs->usb_healthy ||
      elapsed_at_least(inputs->now_ms, control->last_command_ms,
                       JPBB_HOST_COMMAND_TIMEOUT_MS + 1U)) {
    return false;
  }

  /*
   * With a receiver present, CH3 must explicitly grant PC authority.
   * With no receiver at all, an explicit host arm is sufficient.
   */
  pc_permitted = control->receiver_latched
                     ? control->ch3_request == JPBB_CH3_REQUEST_PC
                     : !rc_present(inputs);
  if (!pc_permitted) {
    return false;
  }

  control->pc_armed = true;
  jpbb_control_note_heartbeat(control, inputs->now_ms);
  return true;
}

void jpbb_control_disarm_pc(jpbb_control_t *control) {
  if (control != NULL) {
    control->pc_armed = false;
  }
}

bool jpbb_control_host_ready(const jpbb_control_t *control,
                             const jpbb_control_inputs_t *inputs) {
  if (control == NULL || inputs == NULL || !control->pc_armed ||
      !control->command_received || !control->heartbeat_received ||
      !inputs->usb_healthy) {
    return false;
  }
  return !elapsed_at_least(inputs->now_ms, control->last_command_ms,
                           JPBB_HOST_COMMAND_TIMEOUT_MS + 1U) &&
         !elapsed_at_least(inputs->now_ms, control->last_heartbeat_ms,
                           JPBB_HOST_HEARTBEAT_TIMEOUT_MS + 1U);
}

jpbb_authority_t jpbb_control_update(jpbb_control_t *control,
                                     const jpbb_control_inputs_t *inputs) {
  bool pc_permitted;

  if (control == NULL || inputs == NULL) {
    return JPBB_AUTHORITY_SAFE;
  }

  update_ch3(control, inputs);

  /*
   * Once a complete receiver has been observed, keep requiring its CH3
   * authority signal until reset.  Losing a previously connected receiver
   * must not silently turn the system into receiver-less PC-only mode.
   */
  if (inputs->rc1_valid && inputs->rc2_valid && inputs->rc3_valid) {
    control->receiver_latched = true;
  }

  if (!inputs->vbec_healthy) {
    jpbb_control_disarm_pc(control);
    return JPBB_AUTHORITY_SAFE;
  }

  /*
   * A confirmed CH3 RC request is the operator override.  It also clears a
   * previous PC arm so losing RC later cannot silently acquire PC authority.
   */
  if (control->ch3_request == JPBB_CH3_REQUEST_RC) {
    jpbb_control_disarm_pc(control);
    return (inputs->rc1_valid && inputs->rc2_valid)
               ? JPBB_AUTHORITY_RC
               : JPBB_AUTHORITY_SAFE;
  }

  pc_permitted = control->receiver_latched
                     ? control->ch3_request == JPBB_CH3_REQUEST_PC
                     : !rc_present(inputs);
  if (pc_permitted && jpbb_control_host_ready(control, inputs)) {
    return JPBB_AUTHORITY_PC;
  }

  /*
   * Host or permission failures latch PC control off.  Fresh commands cannot
   * unexpectedly resume motion until the host explicitly arms again.
   */
  jpbb_control_disarm_pc(control);
  return JPBB_AUTHORITY_SAFE;
}

const char *jpbb_authority_name(jpbb_authority_t authority) {
  if (authority == JPBB_AUTHORITY_RC) {
    return "RC";
  }
  if (authority == JPBB_AUTHORITY_PC) {
    return "PC";
  }
  return "SAFE";
}

const char *jpbb_ch3_request_name(jpbb_ch3_request_t request) {
  if (request == JPBB_CH3_REQUEST_RC) {
    return "RC";
  }
  if (request == JPBB_CH3_REQUEST_PC) {
    return "PC";
  }
  return "UNKNOWN";
}
