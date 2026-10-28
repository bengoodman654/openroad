'use strict';

/**
 * Android WebView PT v2 screen-state REFERENCE, not installed app.js.
 * No DOM, networking, map calls or server work. The actual application
 * must adapt these rules inside its existing route coordinator.
 */
class PTScreenState {
  constructor(sendCancel = () => {}) {
    this.sendCancel = sendCancel;
    this.generation = 0;
    this.foreground = null;
    this.displayTicket = null;
    this.guidanceId = null;
    this.options = new Map();
    this.selectedId = null;
    this.cameraEpoch = 0;
    this.stack = ['PT_ROOT'];
    this.childRequests = new Map();
    this.dirtyEdit = false;
    this.remoteCancelErrors = [];
    this.cancelSent = new Set();
  }

  controls() {
    return {
      backVisible: true,
      backEnabled: this.stack.length > 1,
      xVisible: true,
      xEnabled: !!(this.foreground || this.guidanceId || this.displayTicket),
      xPlacement: 'WHERE_TO_RIGHT',
    };
  }

  beginSearch(taskId) {
    if (typeof taskId !== 'string' || taskId.length < 8) {
      throw new Error('Task must have an opaque request identifier');
    }
    this.cancelForeground();
    this.generation += 1;
    const ticket = Object.freeze({taskId, generation: this.generation});
    this.foreground = ticket;
    this.displayTicket = null;
    this.options.clear();
    this.selectedId = null;
    return ticket;
  }

  sameTicket(a, b) {
    return !!a && !!b && a.taskId === b.taskId &&
      a.generation === b.generation;
  }

  cancelForeground() {
    const ticket = this.foreground;
    if (!ticket) return null;
    this.foreground = null;
    this.options.clear();
    this.selectedId = null;
    const key = ticket.taskId + ':' + ticket.generation;
    if (!this.cancelSent.has(key)) {
      this.cancelSent.add(key);
      try {
        this.sendCancel(ticket);
      } catch (err) {
        // The UI remains cancelled. Server acknowledgement remains unknown.
        this.remoteCancelErrors.push({ticket, reason: 'UNKNOWN_REMOTE_STATUS'});
      }
    }
    return ticket;
  }

  x() {
    if (this.foreground) {
      const ticket = this.cancelForeground();
      return {action: 'CANCEL_FOREGROUND', ticket};
    }
    if (this.guidanceId) {
      return {action: 'CONFIRM_STOP_GUIDANCE'};
    }
    if (this.displayTicket) {
      this.displayTicket = null;
      this.options.clear();
      this.selectedId = null;
      return {action: 'CLOSE_RESULT'};
    }
    return {action: 'NO_ACTION'};
  }

  receive(envelope) {
    const ticket = envelope &&
      {taskId: envelope.requestId, generation: envelope.generation};
    if (!this.sameTicket(this.foreground, ticket)) return false;
    if (envelope.outcome !== 'OK' || !Array.isArray(envelope.results)) {
      this.foreground = null;
      this.displayTicket = null;
      this.options.clear();
      return false;
    }
    const unique = new Map();
    for (const result of envelope.results) {
      if (!result || typeof result.id !== 'string' || !result.id ||
          unique.has(result.id)) return false;
      unique.set(result.id, result);
    }
    this.options = unique;
    this.displayTicket = this.foreground;
    this.foreground = null;
    // No automatic selection, navigation handoff or map-camera movement.
    return true;
  }

  userSelect(ticket, itineraryId) {
    if (!this.sameTicket(this.displayTicket, ticket)) return false;
    const option = this.options.get(itineraryId);
    if (!option || option.selectable !== true) return false;
    if (this.selectedId !== itineraryId) {
      this.selectedId = itineraryId;
      this.cameraEpoch += 1;
    }
    return true;
  }

  enrich(ticket, itineraryId, data) {
    if (!this.sameTicket(this.displayTicket, ticket) ||
        itineraryId !== this.selectedId ||
        !this.options.has(itineraryId)) return false;
    const selected = this.options.get(itineraryId);
    this.options.set(itineraryId, {...selected, enrichment: data});
    // Crucially NO automatic camera reset or switching the selection.
    return true;
  }

  setGuidance(itineraryId) {
    if (!itineraryId) throw new Error('Guidance requires route identity');
    this.guidanceId = itineraryId;
  }

  confirmStopGuidance(confirmed) {
    if (!confirmed || !this.guidanceId || this.foreground) return false;
    this.guidanceId = null;
    return true;
  }

  pushScreen(screenId) {
    if (!screenId || this.stack.includes(screenId)) {
      throw new Error('Invalid screen identity');
    }
    this.stack.push(screenId);
  }

  registerChildRequest(screenId, childId) {
    if (!this.stack.includes(screenId) || !childId) {
      throw new Error('Unknown screen or child');
    }
    if (!this.childRequests.has(screenId)) {
      this.childRequests.set(screenId, new Set());
    }
    this.childRequests.get(screenId).add(childId);
  }

  back() {
    if (this.dirtyEdit) return {action: 'CONFIRM_DISCARD_EDIT'};
    if (this.stack.length <= 1) return {action: 'AT_ROOT'};
    const closed = this.stack.pop();
    const children = [...(this.childRequests.get(closed) || [])];
    this.childRequests.delete(closed);
    return {action: 'POP_ONE', screen: closed, cancelChildren: children};
  }

  resolveDirtyEdit(discard) {
    if (!this.dirtyEdit) return {action: 'NOT_DIRTY'};
    if (!discard) return {action: 'KEEP_EDITING'};
    this.dirtyEdit = false;
    return this.back();
  }
}

module.exports = {PTScreenState};
