'use strict';

(function () {

  // ── DATA ──────────────────────────────────────────────────────
  var VEHICULOS   = JSON.parse(document.getElementById('pizarra-vehiculos')?.textContent   || '[]');
  var CONDUCTORES = JSON.parse(document.getElementById('pizarra-conductores')?.textContent || '[]');
  var AYUDANTES   = JSON.parse(document.getElementById('pizarra-ayudantes')?.textContent   || '[]');
  var EQUIPOS_FORMADOS  = JSON.parse(document.getElementById('pizarra-equipos-formados')?.textContent  || '[]');
  var EQUIPOS_EDICION   = JSON.parse(document.getElementById('pizarra-equipos-edicion')?.textContent   || '[]');
  var EQUIPOS_DIA       = JSON.parse(document.getElementById('pizarra-equipos-dia')?.textContent       || '[]');
  var EQUIPOS_FRECUENTES = JSON.parse(document.getElementById('pizarra-equipos-frecuentes')?.textContent || '[]');

  var AJAX_BASE       = '/dashboard/campo/pizarra/';
  var ESTADO_API      = '/dashboard/campo/api/cambiar-estado/';
  var DURACION_API    = '/dashboard/campo/api/actualizar-duracion/';
  var BUSCAR_CLIENTES = AJAX_BASE + 'buscar-clientes/';
  var datePicker = document.getElementById('pizarra-date-picker');

  if (datePicker) {
    datePicker.addEventListener('change', function () {
      if (this.value) this.form.submit();
    });
  }

  document.querySelectorAll('.pizarra-date-card, .calendar-edge-nav, .nav-btn-today').forEach(function (link) {
    link.addEventListener('pointerenter', function () {
      if (!this.href || this.dataset.prefetched) return;
      this.dataset.prefetched = 'true';
      fetch(this.href, { credentials: 'same-origin' }).catch(function () {});
    }, { once: true });
  });

  function focusEightAm() {
    var matrixScroll = document.querySelector('.pizarra-matrix-scroll');
    var eightAmHeader = document.querySelector('.matrix-hour[data-hora="08:00"]');
    if (!matrixScroll || !eightAmHeader) return;
    matrixScroll.scrollTo({
      left: Math.max(0, eightAmHeader.offsetLeft - 168),
      top: 0,
      behavior: 'auto'
    });
  }

  focusEightAm();
  window.addEventListener('pageshow', focusEightAm);

  // ── HELPERS ───────────────────────────────────────────────────
  function csrfToken() {
    var m = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  function ajax(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); });
  }

  function _esc(str) {
    return (str || '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function _formatFecha(isoStr) {
    if (!isoStr) return '';
    var p = isoStr.split('-');
    return p.length < 3 ? isoStr : p[2] + '/' + p[1] + '/' + p[0];
  }

  // ── SNACKBAR ──────────────────────────────────────────────────
  var snackbar   = document.getElementById('pizarra-snackbar');
  var snackTimer = null;

  function showSnack(msg, type) {
    if (!snackbar) return;
    snackbar.textContent = msg;
    snackbar.className   = 'pizarra-snackbar sb-' + (type || 'ok');
    snackbar.removeAttribute('hidden');
    clearTimeout(snackTimer);
    snackTimer = setTimeout(function () { snackbar.setAttribute('hidden', ''); }, 3000);
  }

  // ── MODALS ────────────────────────────────────────────────────
  function openModal(id) {
    var el = document.getElementById(id);
    if (el) el.removeAttribute('hidden');
  }

  function closeModal(id) {
    var el = document.getElementById(id);
    if (el) el.setAttribute('hidden', '');
  }

  // Close on overlay-background click
  document.querySelectorAll('.modal-overlay').forEach(function (ov) {
    ov.addEventListener('click', function (e) {
      if (e.target === ov) ov.setAttribute('hidden', '');
    });
  });

  // [data-close] buttons
  document.querySelectorAll('[data-close]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      closeModal(this.getAttribute('data-close'));
    });
  });

  // ESC key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay:not([hidden])').forEach(function (m) {
        m.setAttribute('hidden', '');
      });
    }
  });

  // ── POPULATE SELECTS / CHECKS ─────────────────────────────────
  // ── MODAL: CREAR EQUIPO ───────────────────────────────────────
  var eqFechaIso       = document.getElementById('eq-fecha-iso');
  var eqVehiculo       = document.getElementById('eq-vehiculo');
  var eqConductor      = document.getElementById('eq-conductor');
  var eqAyudantes      = document.getElementById('eq-ayudantes-checks');
  var eqWarning        = document.getElementById('eq-warning');
  var btnCrearEquipo   = null;
  var modalEquipoTitle = document.getElementById('modal-equipo-title');

  if (eqVehiculo && VEHICULOS.length) {
    populateSelect(eqVehiculo, VEHICULOS, function (v) { return v.placa + ' — ' + v.marca + ' ' + v.modelo; });
  }
  if (eqConductor && CONDUCTORES.length) {
    populateSelect(eqConductor, CONDUCTORES, function (c) { return c.nombre + ' (' + c.dni + ')'; });
  }
  if (eqAyudantes && AYUDANTES.length) {
    populateChecks(eqAyudantes, AYUDANTES, function (a) { return a.nombre + ' (' + a.dni + ')'; });
  }

  function openEquipoModal(fechaIso) {
    if (eqFechaIso)       eqFechaIso.value = fechaIso;
    if (modalEquipoTitle) modalEquipoTitle.textContent = 'Agregar Equipo · ' + _formatFecha(fechaIso);
    if (eqWarning)        eqWarning.setAttribute('hidden', '');
    if (eqVehiculo)       eqVehiculo.value = '';
    if (eqConductor)      eqConductor.value = '';
    if (eqAyudantes)      eqAyudantes.querySelectorAll('input').forEach(function (cb) { cb.checked = false; });
    openModal('modal-equipo');
  }

  if (btnCrearEquipo) {
    btnCrearEquipo.addEventListener('click', function () {
      var fecha       = eqFechaIso  ? eqFechaIso.value           : '';
      var vehiculoId  = eqVehiculo  ? parseInt(eqVehiculo.value)  : 0;
      var conductorId = eqConductor ? parseInt(eqConductor.value) : 0;

      if (!fecha || !vehiculoId || !conductorId) {
        if (eqWarning) {
          eqWarning.textContent = 'Selecciona vehículo y conductor.';
          eqWarning.removeAttribute('hidden');
        }
        return;
      }

      var ayudanteIds = [];
      if (eqAyudantes) {
        eqAyudantes.querySelectorAll('input:checked').forEach(function (cb) {
          ayudanteIds.push(parseInt(cb.value));
        });
      }

      btnCrearEquipo.disabled = true;

      ajax(AJAX_BASE + 'equipo/crear/', {
        fecha: fecha, vehiculo_id: vehiculoId, conductor_id: conductorId, ayudante_ids: ayudanteIds,
      }).then(function (res) {
        btnCrearEquipo.disabled = false;
        if (res.ok) {
          closeModal('modal-equipo');
          var hasWarn = res.data.warnings && res.data.warnings.length;
          showSnack(hasWarn ? res.data.warnings.join(' ') : 'Equipo creado', hasWarn ? 'warn' : 'ok');
          setTimeout(function () { window.location.reload(); }, 600);
        } else {
          if (eqWarning) {
            eqWarning.textContent = res.data.error || 'Error';
            eqWarning.removeAttribute('hidden');
          }
        }
      }).catch(function () {
        btnCrearEquipo.disabled = false;
        showSnack('Error de red', 'error');
      });
    });
  }

  // ── MODAL: NUEVA RESERVA ──────────────────────────────────────
  var equipoModal       = document.getElementById('modal-equipo');
  var eqFormedGrid      = document.getElementById('eq-formed-grid');
  var eqFormedEmpty     = document.getElementById('eq-formed-empty');
  var eqDiaGrid         = document.getElementById('eq-dia-grid');
  var eqDiaEmpty        = document.getElementById('eq-dia-empty');
  var eqFrecGrid        = document.getElementById('eq-frec-grid');
  var eqFrecEmpty       = document.getElementById('eq-frec-empty');
  var eqPanelDia        = document.getElementById('eq-panel-dia');
  var eqPanelFrecuentes = document.getElementById('eq-panel-frecuentes');
  var eqPanelCrear      = document.getElementById('eq-panel-crear');
  var eqVehiculosList   = document.getElementById('eq-vehiculos-list');
  var eqConductoresList = document.getElementById('eq-conductores-list');
  var eqAyudantesList   = document.getElementById('eq-ayudantes-list');
  var btnAgregarEquipo  = document.getElementById('btn-crear-equipo');
  var equipoState = {
    mode: 'dia',
    editingId: null,
    formadoId: null,
    frecuenteId: null,
    vehiculoId: null,
    conductorId: null,
    conductorAyudanteIds: [],
    ayudanteIds: [],
  };

  function initials(name) {
    return (name || '').split(/\s+/).slice(0, 2).map(function (part) {
      return part.charAt(0).toUpperCase();
    }).join('');
  }

  function renderEquiposFormados() {
    if (!eqFormedGrid || !eqFormedEmpty) return;
    eqFormedGrid.innerHTML = '';
    eqFormedEmpty.toggleAttribute('hidden', EQUIPOS_FORMADOS.length > 0);
    EQUIPOS_FORMADOS.forEach(function (equipo) {
      var ayudantes = (equipo.ayudantes || []).concat(equipo.conductores_ayudantes || []);
      var card = document.createElement('button');
      card.type = 'button';
      card.className = 'eq-formed-card';
      card.dataset.equipoId = equipo.id;
      card.innerHTML =
        '<div class="eq-formed-plate">' + _esc(equipo.placa) + '</div>' +
        '<div class="eq-formed-vehicle">' + _esc(equipo.vehiculo) + '</div>' +
        '<div class="eq-formed-person"><span class="mdi mdi-account-tie"></span>' +
          _esc(equipo.conductor) + '</div>' +
        '<div class="eq-formed-helpers"><span class="mdi mdi-account-multiple"></span> ' +
          (ayudantes.length ? _esc(ayudantes.join(', ')) : 'Sin ayudantes') + '</div>';
      eqFormedGrid.appendChild(card);
    });
  }

  function renderEquiposDia(highlightId) {
    if (!eqDiaGrid || !eqDiaEmpty) return;
    var fecha = eqFechaIso ? eqFechaIso.value : '';
    var lista = EQUIPOS_DIA.filter(function (eq) { return !fecha || eq.fecha === fecha; });
    eqDiaGrid.innerHTML = '';
    eqDiaEmpty.toggleAttribute('hidden', lista.length > 0);
    lista.forEach(function (eq) {
      var isHL = highlightId && eq.id === highlightId;
      var card = document.createElement('div');
      card.className = 'eq-formed-card eq-dia-card' + (isHL ? ' selected' : '');
      card.dataset.id = eq.id;
      card.innerHTML =
        '<div class="eq-formed-plate">' + _esc(eq.placa) + '</div>' +
        '<div class="eq-formed-person"><span class="mdi mdi-account-tie"></span>' + _esc(eq.conductor) + '</div>' +
        '<div class="eq-formed-helpers"><span class="mdi mdi-account-multiple"></span> ' +
          (eq.ayudantes && eq.ayudantes.length ? _esc(eq.ayudantes.join(', ')) : 'Sin ayudantes') + '</div>' +
        '<div style="font-size:11px;color:#94a3b8;margin-top:2px;"><span class="mdi mdi-calendar-check"></span> ' + (eq.n_reservas || 0) + ' reservas</div>' +
        '<button type="button" class="eq-dia-edit-btn" data-equipo-id="' + eq.id + '">' +
          '<span class="mdi mdi-pencil-outline"></span> Editar</button>';
      eqDiaGrid.appendChild(card);
    });
  }

  function _fillBuilderFromEquipo(equipo) {
    document.querySelectorAll('.eq-builder-item.selected, .eq-role-check.active').forEach(function (el) {
      el.classList.remove('selected', 'active');
    });
    document.querySelectorAll('#eq-panel-crear input[type="radio"], #eq-panel-crear input[type="checkbox"]').forEach(function (i) { i.checked = false; });
    equipoState.editingId = equipo.id;
    equipoState.vehiculoId = equipo.vehiculo_id;
    equipoState.conductorId = equipo.conductor_id;
    equipoState.ayudanteIds = (equipo.ayudante_ids || []).slice();
    equipoState.conductorAyudanteIds = (equipo.conductor_ayudante_ids || []).slice();
    var vInput = document.querySelector('input[name="eq-vehiculo-radio"][value="' + equipo.vehiculo_id + '"]');
    if (vInput) { vInput.checked = true; vInput.closest('.eq-builder-item').classList.add('selected'); }
    document.querySelectorAll('#eq-conductores-list .eq-builder-item').forEach(function (item) {
      var id = parseInt(item.dataset.id);
      var isCond = id === equipo.conductor_id;
      var isHelp = (equipo.conductor_ayudante_ids || []).indexOf(id) !== -1;
      item.classList.toggle('selected', isCond || isHelp);
      var cb = item.querySelector('[data-role="conductor"]');
      var hb = item.querySelector('[data-role="ayudante"]');
      if (cb) cb.classList.toggle('active', isCond);
      if (hb) hb.classList.toggle('active', isHelp);
    });
    document.querySelectorAll('.eq-ayudante-check').forEach(function (input) {
      var checked = (equipo.ayudante_ids || []).indexOf(parseInt(input.value)) !== -1;
      input.checked = checked;
      input.closest('.eq-builder-item').classList.toggle('selected', checked);
    });
    if (btnAgregarEquipo) btnAgregarEquipo.innerHTML = '<span class="mdi mdi-content-save"></span> Guardar cambios';
    var formadosInner = document.getElementById('eq-panel-formados-inner');
    if (formadosInner) formadosInner.setAttribute('hidden', '');
    updateEquipoSummary();
  }

  function renderEquiposFrecuentes() {
    if (!eqFrecGrid || !eqFrecEmpty) return;
    eqFrecGrid.innerHTML = '';
    eqFrecEmpty.toggleAttribute('hidden', EQUIPOS_FRECUENTES.length > 0);
    EQUIPOS_FRECUENTES.forEach(function (ef) {
      var all = (ef.ayudantes || []).concat(ef.conductores_ayudantes || []);
      var card = document.createElement('button');
      card.type = 'button';
      card.className = 'eq-formed-card';
      card.dataset.frecuenteId = ef.id;
      card.innerHTML =
        '<div class="eq-formed-plate">' + _esc(ef.placa) + '</div>' +
        '<div class="eq-formed-vehicle">' + _esc(ef.nombre) + '</div>' +
        '<div class="eq-formed-person"><span class="mdi mdi-account-tie"></span>' + _esc(ef.conductor) + '</div>' +
        '<div class="eq-formed-helpers"><span class="mdi mdi-account-multiple"></span> ' +
          (all.length ? _esc(all.join(', ')) : 'Sin ayudantes') + '</div>';
      eqFrecGrid.appendChild(card);
    });
  }

  function renderBuilderLists() {
    if (eqVehiculosList) {
      eqVehiculosList.innerHTML = VEHICULOS.map(function (v) {
        return '<label class="eq-builder-item vehicle" data-search="' +
          _esc((v.placa + ' ' + v.marca + ' ' + v.modelo).toLowerCase()) + '">' +
          '<input type="radio" name="eq-vehiculo-radio" value="' + v.id + '">' +
          '<span><span class="eq-builder-name">' + _esc(v.placa) + '</span>' +
          '<span class="eq-builder-meta">' + _esc(v.marca + ' ' + v.modelo) + '</span></span></label>';
      }).join('');
    }
    if (eqConductoresList) {
      eqConductoresList.innerHTML = CONDUCTORES.map(function (c) {
        return '<div class="eq-builder-item conductor" data-id="' + c.id +
          '" data-name="' + _esc(c.nombre) + '" data-search="' +
          _esc((c.nombre + ' ' + c.dni).toLowerCase()) + '">' +
          '<span class="eq-builder-name">' + _esc(c.nombre) + '</span>' +
          '<div class="eq-role-checks">' +
          '<button type="button" class="eq-role-check" data-role="conductor" title="Conductor principal">C</button>' +
          '<button type="button" class="eq-role-check" data-role="ayudante" title="Agregar como ayudante">A</button>' +
          '</div></div>';
      }).join('');
    }
    if (eqAyudantesList) {
      eqAyudantesList.innerHTML = AYUDANTES.map(function (a) {
        return '<label class="eq-builder-item ayudante" data-search="' +
          _esc((a.nombre + ' ' + a.dni).toLowerCase()) + '">' +
          '<input type="checkbox" class="eq-ayudante-check" value="' + a.id + '">' +
          '<span><span class="eq-builder-name">' + _esc(a.nombre) + '</span>' +
          '<span class="eq-builder-meta">' + _esc(a.dni) + '</span></span></label>';
      }).join('');
    }
  }

  function setEquipoMode(mode) {
    equipoState.mode = mode;
    document.querySelectorAll('.eq-mode-tab').forEach(function (tab) {
      tab.classList.toggle('active', tab.dataset.eqMode === mode);
    });
    if (eqPanelDia)        eqPanelDia.toggleAttribute('hidden',        mode !== 'dia');
    if (eqPanelFrecuentes) eqPanelFrecuentes.toggleAttribute('hidden', mode !== 'frecuentes');
    if (eqPanelCrear)      eqPanelCrear.toggleAttribute('hidden',      mode !== 'crear');
    updateEquipoButton();
  }

  function resetEquipoState() {
    equipoState.editingId = null;
    equipoState.formadoId = null;
    equipoState.frecuenteId = null;
    equipoState.vehiculoId = null;
    equipoState.conductorId = null;
    equipoState.conductorAyudanteIds = [];
    equipoState.ayudanteIds = [];
    document.querySelectorAll('.eq-formed-card.selected, .eq-builder-item.selected, .eq-role-check.active').forEach(function (el) {
      el.classList.remove('selected', 'active');
    });
    document.querySelectorAll('#eq-panel-crear input').forEach(function (input) {
      input.checked = false;
      input.value = input.type === 'search' ? '' : input.value;
    });
    if (eqWarning) eqWarning.setAttribute('hidden', '');
    var formadosInner = document.getElementById('eq-panel-formados-inner');
    if (formadosInner) formadosInner.removeAttribute('hidden');
    updateEquipoSummary();
    if (btnAgregarEquipo) {
      btnAgregarEquipo.innerHTML = '<span class="mdi mdi-check"></span> Agregar a Pizarra';
    }
  }

  function updateEquipoSummary() {
    var vehiculo = VEHICULOS.find(function (v) { return v.id === equipoState.vehiculoId; });
    var conductor = CONDUCTORES.find(function (c) { return c.id === equipoState.conductorId; });
    var nombres = [];
    equipoState.conductorAyudanteIds.forEach(function (id) {
      var item = CONDUCTORES.find(function (c) { return c.id === id; });
      if (item) nombres.push(item.nombre);
    });
    equipoState.ayudanteIds.forEach(function (id) {
      var item = AYUDANTES.find(function (a) { return a.id === id; });
      if (item) nombres.push(item.nombre);
    });
    var sv = document.getElementById('eq-summary-v');
    var sc = document.getElementById('eq-summary-c');
    var sa = document.getElementById('eq-summary-a');
    if (sv) sv.textContent = vehiculo ? vehiculo.placa : 'Sin vehículo';
    if (sc) sc.textContent = conductor ? conductor.nombre : 'Sin conductor';
    if (sa) sa.textContent = nombres.length ? nombres.join(', ') : 'Sin ayudantes';
    updateEquipoButton();
  }

  function validarEquipo() {
    if (equipoState.mode === 'dia') return { valid: false, message: '' };
    if (equipoState.mode === 'frecuentes') return { valid: !!equipoState.frecuenteId, message: '' };

    var errors = [];
    var warnings = [];
    var fecha = eqFechaIso ? eqFechaIso.value : '';

    if (equipoState.vehiculoId && equipoState.conductorId) {
      // Validar si ya existe equipo con mismo vehículo + conductor en el mismo día
      var existe = EQUIPOS_DIA.some(function (eq) {
        return eq.fecha === fecha &&
               eq.vehiculo_id === equipoState.vehiculoId &&
               eq.conductor_id === equipoState.conductorId &&
               eq.id !== equipoState.editingId;
      });
      if (existe) {
        errors.push('⚠ Equipo con este vehículo y conductor ya existe hoy');
      }

      // Validar if conductor aparece en ayudantes
      if (equipoState.conductorAyudanteIds.indexOf(equipoState.conductorId) !== -1) {
        errors.push('❌ El conductor no puede ser su propio ayudante');
      }

      // Avisar si vehículo está en otro conductor
      var otroCondVehículo = EQUIPOS_DIA.some(function (eq) {
        return eq.fecha === fecha &&
               eq.vehiculo_id === equipoState.vehiculoId &&
               eq.conductor_id !== equipoState.conductorId &&
               eq.id !== equipoState.editingId;
      });
      if (otroCondVehículo) {
        warnings.push('⚠ Este vehículo tiene otro conductor el mismo día');
      }

      // Avisar si conductor tiene múltiples equipos
      var multEquipo = EQUIPOS_DIA.filter(function (eq) {
        return eq.fecha === fecha &&
               eq.conductor_id === equipoState.conductorId &&
               eq.id !== equipoState.editingId;
      }).length > 0;
      if (multEquipo) {
        warnings.push('⚠ Este conductor tiene otro equipo el mismo día');
      }
    }

    var message = '';
    if (errors.length) {
      message = errors.join(' · ');
    } else if (warnings.length) {
      message = warnings.join(' · ');
    }

    return {
      valid: errors.length === 0 && (equipoState.formadoId || (equipoState.vehiculoId && equipoState.conductorId)),
      message: message,
      isWarning: errors.length === 0 && warnings.length > 0
    };
  }

  function updateEquipoButton() {
    if (!btnAgregarEquipo) return;
    var validation = validarEquipo();
    btnAgregarEquipo.disabled = !validation.valid;

    if (eqWarning) {
      if (validation.message) {
        eqWarning.textContent = validation.message;
        eqWarning.className = 'form-warning' + (validation.isWarning ? ' form-warning-alert' : ' form-warning-error');
        eqWarning.removeAttribute('hidden');
      } else {
        eqWarning.setAttribute('hidden', '');
      }
    }
  }

  function openEquipoModal(fechaIso) {
    if (eqFechaIso) eqFechaIso.value = fechaIso;
    if (modalEquipoTitle) modalEquipoTitle.textContent = 'Agregar Equipo · ' + _formatFecha(fechaIso);
    resetEquipoState();
    renderEquiposDia();
    var diaCount = EQUIPOS_DIA.filter(function (eq) { return eq.fecha === fechaIso; }).length;
    var defaultMode = diaCount ? 'dia'
      : EQUIPOS_FRECUENTES.length ? 'frecuentes'
      : 'crear';
    setEquipoMode(defaultMode);
    openModal('modal-equipo');
  }

  function openEquipoEditModal(equipoId) {
    var equipo = EQUIPOS_EDICION.find(function (item) { return item.id === equipoId; });
    if (!equipo) return;
    resetEquipoState();
    if (modalEquipoTitle) modalEquipoTitle.textContent = 'Editar Equipo';
    renderEquiposDia(equipoId);
    setEquipoMode('dia');
    // Pre-fill builder but don't switch to it yet
    _fillBuilderFromEquipo(equipo);
    openModal('modal-equipo');
  }

  renderEquiposFormados();
  renderEquiposDia();
  renderEquiposFrecuentes();
  renderBuilderLists();

  if (equipoModal) {
    equipoModal.addEventListener('click', function (e) {
      var modeTab = e.target.closest('.eq-mode-tab');
      if (modeTab) {
        setEquipoMode(modeTab.dataset.eqMode);
        return;
      }

      var diaEditBtn = e.target.closest('.eq-dia-edit-btn');
      if (diaEditBtn) {
        var eqId = parseInt(diaEditBtn.dataset.equipoId);
        var eqData = EQUIPOS_EDICION.find(function (x) { return x.id === eqId; });
        if (eqData) {
          _fillBuilderFromEquipo(eqData);
          setEquipoMode('crear');
        }
        return;
      }

      var formedCard = e.target.closest('.eq-formed-card');
      if (formedCard) {
        if (formedCard.dataset.frecuenteId) {
          equipoState.frecuenteId = parseInt(formedCard.dataset.frecuenteId);
          document.querySelectorAll('#eq-frec-grid .eq-formed-card').forEach(function (card) {
            card.classList.toggle('selected', card === formedCard);
          });
        } else if (formedCard.dataset.equipoId) {
          equipoState.formadoId = parseInt(formedCard.dataset.equipoId);
          document.querySelectorAll('#eq-formed-grid .eq-formed-card').forEach(function (card) {
            card.classList.toggle('selected', card === formedCard);
          });
        }
        updateEquipoButton();
        return;
      }

      var roleButton = e.target.closest('.eq-role-check');
      if (roleButton) {
        var item = roleButton.closest('.eq-builder-item');
        var id = parseInt(item.dataset.id);
        if (roleButton.dataset.role === 'conductor') {
          if (equipoState.conductorAyudanteIds.indexOf(id) !== -1) return;
          equipoState.conductorId = equipoState.conductorId === id ? null : id;
          document.querySelectorAll('[data-role="conductor"]').forEach(function (button) {
            button.classList.toggle('active', button === roleButton && equipoState.conductorId === id);
          });
        } else {
          if (equipoState.conductorId === id) return;
          var helperIndex = equipoState.conductorAyudanteIds.indexOf(id);
          if (helperIndex === -1) {
            equipoState.conductorAyudanteIds.push(id);
            roleButton.classList.add('active');
          } else {
            equipoState.conductorAyudanteIds.splice(helperIndex, 1);
            roleButton.classList.remove('active');
          }
        }
        document.querySelectorAll('#eq-conductores-list .eq-builder-item').forEach(function (conductorItem) {
          var conductorItemId = parseInt(conductorItem.dataset.id);
          conductorItem.classList.toggle(
            'selected',
            equipoState.conductorId === conductorItemId ||
              equipoState.conductorAyudanteIds.indexOf(conductorItemId) !== -1
          );
        });
        updateEquipoSummary();
      }
    });

    equipoModal.addEventListener('change', function (e) {
      if (e.target.matches('input[name="eq-vehiculo-radio"]')) {
        equipoState.vehiculoId = parseInt(e.target.value);
        document.querySelectorAll('#eq-vehiculos-list .eq-builder-item').forEach(function (item) {
          item.classList.toggle('selected', item.contains(e.target));
        });
      }
      if (e.target.matches('.eq-ayudante-check')) {
        var id = parseInt(e.target.value);
        var index = equipoState.ayudanteIds.indexOf(id);
        if (e.target.checked && index === -1) equipoState.ayudanteIds.push(id);
        if (!e.target.checked && index !== -1) equipoState.ayudanteIds.splice(index, 1);
        e.target.closest('.eq-builder-item').classList.toggle('selected', e.target.checked);
      }
      updateEquipoSummary();
    });

    equipoModal.addEventListener('input', function (e) {
      if (!e.target.matches('.eq-builder-search')) return;
      var query = e.target.value.toLowerCase().trim();
      var listId = 'eq-' + e.target.dataset.eqSearch + '-list';
      document.querySelectorAll('#' + listId + ' .eq-builder-item').forEach(function (item) {
        item.style.display = !query || item.dataset.search.indexOf(query) !== -1 ? '' : 'none';
      });
    });
  }

  if (btnAgregarEquipo) {
    btnAgregarEquipo.addEventListener('click', function () {
      if (btnAgregarEquipo.disabled) return;
      var fecha = eqFechaIso ? eqFechaIso.value : '';
      var payload, equipoUrl;

      if (equipoState.mode === 'frecuentes') {
        payload = { fecha: fecha, frecuente_id: equipoState.frecuenteId };
        equipoUrl = AJAX_BASE + 'equipo/desde-frecuente/';
      } else if (!equipoState.editingId && equipoState.formadoId) {
        payload = { fecha: fecha, equipo_origen_id: equipoState.formadoId };
        equipoUrl = AJAX_BASE + 'equipo/crear/';
      } else {
        payload = {
          fecha: fecha,
          vehiculo_id: equipoState.vehiculoId,
          conductor_id: equipoState.conductorId,
          conductor_ayudante_ids: equipoState.conductorAyudanteIds,
          ayudante_ids: equipoState.ayudanteIds,
        };
        equipoUrl = equipoState.editingId
          ? '/dashboard/campo/equipos/' + equipoState.editingId + '/editar-ajax/'
          : AJAX_BASE + 'equipo/crear/';
      }

      btnAgregarEquipo.disabled = true;
      ajax(equipoUrl, payload).then(function (res) {
        if (!res.ok) {
          btnAgregarEquipo.disabled = false;
          if (eqWarning) {
            eqWarning.textContent = res.data.error || 'Error al agregar equipo';
            eqWarning.removeAttribute('hidden');
          }
          return;
        }
        closeModal('modal-equipo');
        showSnack(
          equipoState.editingId ? 'Equipo actualizado' : 'Equipo agregado a la Pizarra',
          res.data.warnings && res.data.warnings.length ? 'warn' : 'ok'
        );
        setTimeout(function () { window.location.reload(); }, 600);
      }).catch(function () {
        btnAgregarEquipo.disabled = false;
        showSnack('Error de red', 'error');
      });
    });
  }

  var resEquipoId       = document.getElementById('res-equipo-id');
  var resFecha          = document.getElementById('res-fecha');
  var resHora           = document.getElementById('res-hora');
  var resEquipoDisplay  = document.getElementById('res-equipo-display');
  var resHoraDisplay    = document.getElementById('res-hora-display');
  var resDuracion       = document.getElementById('res-duracion');
  var resBuscar         = document.getElementById('res-buscar');
  var resAutocomplete   = document.getElementById('res-autocomplete');
  var resClienteId      = document.getElementById('res-cliente-id');
  var resNombre         = document.getElementById('res-nombre');
  var resTelefono       = document.getElementById('res-telefono');
  var resDocumento      = document.getElementById('res-documento');
  var resCorreo         = document.getElementById('res-correo');
  var resRuc            = document.getElementById('res-ruc');
  var resRazonSocial    = document.getElementById('res-razon-social');
  var resPrecio         = document.getElementById('res-precio');
  var resTipoComprobante= document.getElementById('res-tipo-comprobante');
  var resOrigen         = document.getElementById('res-origen');
  var resDestino        = document.getElementById('res-destino');
  var resPisoOrigen     = document.getElementById('res-piso-origen');
  var resPisoDestino    = document.getElementById('res-piso-destino');
  var resDetalleCarga   = document.getElementById('res-detalle-carga');
  var resObs            = document.getElementById('res-obs');
  var resWarning        = document.getElementById('res-warning');
  var btnCrearReserva   = document.getElementById('btn-crear-reserva');
  var modalReservaTitle = document.getElementById('modal-reserva-title');
  var resBadgeExistente = document.getElementById('res-badge-existente');
  var resEmpresaToggle  = document.getElementById('res-empresa-toggle');
  var resEmpresaArrow   = document.getElementById('res-empresa-arrow');
  var resEmpresaContent = document.getElementById('res-empresa-content');

  function openReservaModal(fecha, hora, equipoId, equipoLabel) {
    if (resFecha)          resFecha.value         = fecha;
    if (resHora)           resHora.value           = hora;
    if (resEquipoId)       resEquipoId.value       = equipoId;
    if (resEquipoDisplay)  resEquipoDisplay.value  = equipoLabel + ' · ' + _formatFecha(fecha);
    if (resHoraDisplay)    resHoraDisplay.value    = hora;
    if (modalReservaTitle) modalReservaTitle.textContent = 'Nueva Reserva · ' + equipoLabel + ' · ' + hora;
    if (resWarning)        resWarning.setAttribute('hidden', '');
    [resBuscar, resNombre, resTelefono, resPrecio, resOrigen, resDestino, resObs,
     resDocumento, resCorreo, resRuc, resRazonSocial,
     resPisoOrigen, resPisoDestino, resDetalleCarga].forEach(function (el) {
      if (el) el.value = '';
    });
    if (resClienteId) resClienteId.value = '';
    if (resAutocomplete) resAutocomplete.setAttribute('hidden', '');
    if (resBadgeExistente) resBadgeExistente.setAttribute('hidden', '');
    if (resEmpresaContent) resEmpresaContent.setAttribute('hidden', '');
    if (resEmpresaToggle) resEmpresaToggle.classList.remove('open');
    // Reset pills
    document.querySelectorAll('.res-pill.active').forEach(function (p) { p.classList.remove('active'); });
    document.querySelectorAll('.res-pill input[type="radio"]').forEach(function (r) {
      if (r.defaultChecked) { r.checked = true; r.closest('.res-pill').classList.add('active'); }
    });
    // Reset requisitos
    document.querySelectorAll('.res-check-chip.active').forEach(function (c) { c.classList.remove('active'); });
    document.querySelectorAll('.res-req-chk').forEach(function (c) {
      c.checked = c.value === 'ninguno';
      if (c.checked) c.closest('.res-check-chip').classList.add('active');
    });
    openModal('modal-reserva');
  }

  // Autocomplete
  var acTimer = null;

  if (resBuscar) {
    resBuscar.addEventListener('input', function () {
      clearTimeout(acTimer);
      var q = this.value.trim();
      if (q.length < 2) { if (resAutocomplete) resAutocomplete.setAttribute('hidden', ''); return; }
      acTimer = setTimeout(function () {
        fetch(BUSCAR_CLIENTES + '?q=' + encodeURIComponent(q))
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!resAutocomplete) return;
            resAutocomplete.innerHTML = '';
            if (!data.clientes || !data.clientes.length) {
              resAutocomplete.setAttribute('hidden', ''); return;
            }
            data.clientes.forEach(function (c) {
              var div = document.createElement('div');
              div.className = 'ac-item';
              div.innerHTML =
                '<span class="ac-nombre">' + _esc(c.nombre || '—') + '</span>' +
                '<span class="ac-tel">' + _esc(c.telefono) + '</span>';
              div.addEventListener('click', function () {
                if (resNombre)   resNombre.value   = c.nombre || '';
                if (resTelefono) resTelefono.value = c.telefono;
                if (resDocumento) resDocumento.value = c.documento || '';
                if (resCorreo)   resCorreo.value   = c.correo || '';
                if (resRuc)      resRuc.value      = c.ruc || '';
                if (resRazonSocial) resRazonSocial.value = c.razon_social || '';
                if (resClienteId) resClienteId.value = c.id || '';
                if (resBuscar)   resBuscar.value   = '';
                if (resBadgeExistente) resBadgeExistente.removeAttribute('hidden');
                resAutocomplete.setAttribute('hidden', '');
              });
              resAutocomplete.appendChild(div);
            });
            resAutocomplete.removeAttribute('hidden');
          });
      }, 300);
    });

    document.addEventListener('click', function (e) {
      if (resAutocomplete && resBuscar &&
          !resBuscar.contains(e.target) && !resAutocomplete.contains(e.target)) {
        resAutocomplete.setAttribute('hidden', '');
      }
    });
  }

  // ── UI: empresa toggle ──────────────────────────────────────
  if (resEmpresaToggle && resEmpresaContent) {
    resEmpresaToggle.addEventListener('click', function () {
      var open = !resEmpresaContent.hasAttribute('hidden');
      if (open) {
        resEmpresaContent.setAttribute('hidden', '');
        resEmpresaToggle.classList.remove('open');
      } else {
        resEmpresaContent.removeAttribute('hidden');
        resEmpresaToggle.classList.add('open');
      }
    });
  }

  // ── UI: pill/chip toggles ───────────────────────────────────
  document.querySelectorAll('.res-pill').forEach(function (pill) {
    pill.addEventListener('click', function () {
      var input = this.querySelector('input');
      if (!input) return;
      if (input.type === 'radio') {
        var name = input.name;
        document.querySelectorAll('.res-pill input[name="' + name + '"]').forEach(function (r) {
          r.checked = false;
          r.closest('.res-pill').classList.remove('active');
        });
        input.checked = true;
        this.classList.add('active');
      } else if (input.type === 'checkbox') {
        input.checked = !input.checked;
        this.classList.toggle('active', input.checked);
      }
    });
  });

  document.querySelectorAll('.res-check-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var cb = this.querySelector('input[type="checkbox"]');
      if (!cb) return;
      cb.checked = !cb.checked;
      this.classList.toggle('active', cb.checked);
      // "Ninguno" logic
      if (cb.value === 'ninguno' && cb.checked) {
        document.querySelectorAll('.res-req-chk:not([value="ninguno"])').forEach(function (o) {
          o.checked = false;
          o.closest('.res-check-chip').classList.remove('active');
        });
      } else if (cb.value !== 'ninguno' && cb.checked) {
        var n = document.querySelector('.res-req-chk[value="ninguno"]');
        if (n) { n.checked = false; n.closest('.res-check-chip').classList.remove('active'); }
      }
      // If none selected, re-check ninguno
      if (!document.querySelectorAll('.res-req-chk:checked').length) {
        var nn = document.querySelector('.res-req-chk[value="ninguno"]');
        if (nn) { nn.checked = true; nn.closest('.res-check-chip').classList.add('active'); }
      }
    });
  });

  // ── helpers ──────────────────────────────────────────────────
  function _getCheckedAcceso(name) {
    var vals = [];
    document.querySelectorAll('input.res-acceso-chk[name="' + name + '"]:checked').forEach(function (c) {
      vals.push(c.value);
    });
    return vals;
  }

  function _getCheckedRequisitos() {
    var vals = [];
    document.querySelectorAll('.res-req-chk:checked').forEach(function (c) {
      vals.push(c.value);
    });
    return vals;
  }

  function _getRadioValue(name) {
    var sel = document.querySelector('input[type="radio"][name="' + name + '"]:checked');
    return sel ? sel.value : '';
  }

  if (btnCrearReserva) {
    btnCrearReserva.addEventListener('click', function () {
      var equipoId = resEquipoId ? resEquipoId.value        : '';
      var fecha    = resFecha    ? resFecha.value            : '';
      var hora     = resHora     ? resHora.value             : '';
      var duracion = resDuracion ? resDuracion.value         : '1';
      var clienteId = resClienteId ? resClienteId.value      : '';
      var nombre   = resNombre   ? resNombre.value.trim()    : '';
      var telefono = resTelefono ? resTelefono.value.trim()  : '';
      var documento= resDocumento ? resDocumento.value.trim(): '';
      var correo   = resCorreo   ? resCorreo.value.trim()    : '';
      var ruc      = resRuc      ? resRuc.value.trim()       : '';
      var razonSocial = resRazonSocial ? resRazonSocial.value.trim() : '';
      var precio   = resPrecio   ? resPrecio.value           : '';
      var tipoComp = _getRadioValue('tipo_comprobante');
      var origen   = resOrigen   ? resOrigen.value.trim()    : '';
      var destino  = resDestino  ? resDestino.value.trim()   : '';
      var pisoOrigen  = resPisoOrigen ? resPisoOrigen.value.trim()  : '';
      var pisoDestino = resPisoDestino ? resPisoDestino.value.trim() : '';
      var accesoOrigen  = _getCheckedAcceso('acceso_origen');
      var accesoDestino = _getCheckedAcceso('acceso_destino');
      var detalleCarga  = resDetalleCarga ? resDetalleCarga.value.trim() : '';
      var tipoEmb = _getRadioValue('tipo_embalaje');
      var reqs    = _getCheckedRequisitos();
      var obs      = resObs      ? resObs.value.trim()       : '';

      if (!nombre || !telefono || !origen || !destino) {
        if (resWarning) {
          resWarning.textContent = 'Nombre, teléfono, origen y destino son requeridos.';
          resWarning.removeAttribute('hidden');
        }
        return;
      }

      btnCrearReserva.disabled = true;

      ajax(AJAX_BASE + 'programacion/crear/', {
        equipo_id: parseInt(equipoId) || null,
        fecha: fecha, hora: hora, duracion: duracion,
        cliente_id: clienteId ? parseInt(clienteId) : null,
        nombre: nombre, telefono: telefono, documento: documento,
        correo: correo, ruc: ruc, razon_social: razonSocial,
        precio: precio, tipo_comprobante: tipoComp,
        origen: origen, destino: destino,
        piso_origen: pisoOrigen, piso_destino: pisoDestino,
        acceso_origen: accesoOrigen, acceso_destino: accesoDestino,
        detalle_carga: detalleCarga,
        tipo_embalaje: tipoEmb, requisitos: reqs,
        observaciones: obs,
      }).then(function (res) {
        btnCrearReserva.disabled = false;
        if (res.ok) {
          closeModal('modal-reserva');
          showSnack('Reserva ' + (res.data.servicio_codigo || '') + ' creada', 'ok');
          setTimeout(function () { window.location.reload(); }, 700);
        } else {
          if (resWarning) {
            resWarning.textContent = res.data.error || 'Error';
            resWarning.removeAttribute('hidden');
          }
        }
      }).catch(function () {
        btnCrearReserva.disabled = false;
        showSnack('Error de red', 'error');
      });
    });
  }

  // ── MODAL: ASIGNAR RESERVA SIN EQUIPO ─────────────────────────
  var mmrAsignar  = document.getElementById('mmr-asignar');
  var mmrTeamSelect = document.getElementById('mmr-team-select');
  var _mmrUnassignedPsId = null;
  var _mmrUnassignedSvId = null;

  function openUnassignedMenu(card) {
    var psId    = card.getAttribute('data-ps-id');
    var svId    = card.getAttribute('data-servicio-id');
    var fecha   = card.getAttribute('data-fecha');
    var hora    = card.getAttribute('data-hora') || '—';
    _mmrUnassignedPsId = (psId && /^\d+$/.test(psId)) ? psId : null;
    _mmrUnassignedSvId = (svId && /^\d+$/.test(svId)) ? svId : null;
    _mmrUnassignedFecha = fecha || '';
    _mmrUnassignedHora = (hora !== '—') ? hora : '';

    var codigo  = card.querySelector('.unassigned-main span')?.textContent?.split('·')[0]?.trim() || '—';
    var cliente = card.querySelector('.unassigned-main span')?.textContent?.split('·')[1]?.trim() || '—';
    var monto   = card.querySelector('.unassigned-main strong')?.textContent?.split('·')[1]?.trim() || '';

    if (mmrTitle) mmrTitle.textContent = (codigo || '—') + ' — ' + (cliente || '—');
    if (mmrInfo) {
      mmrInfo.innerHTML =
        '<strong>' + _esc(cliente) + '</strong><br>' +
        '<span style="color:#64748b;">' + _esc(hora) + '</span><br>' +
        (monto ? '<span style="font-weight:700;">' + _esc(monto) + '</span>' : '');
    }

    // populate team select from matrix-team-row elements in same day section
    if (mmrTeamSelect) {
      mmrTeamSelect.innerHTML = '<option value="">— Seleccionar —</option>';
      var daySection = card.closest('.matrix-day');
      if (!daySection) {
        var fechaCard = card.getAttribute('data-fecha');
        if (fechaCard) daySection = document.querySelector('.matrix-day[data-fecha="' + fechaCard + '"]');
      }
      if (!daySection) daySection = document.querySelector('.matrix-day');
      var teamRows = daySection ? daySection.querySelectorAll('.matrix-team-row') : [];
      teamRows.forEach(function (row) {
        var id = row.getAttribute('data-equipo-id');
        var placa = row.querySelector('.eq-placa')?.textContent?.trim() || 'Equipo';
        var conductor = row.querySelector('.eq-conductor')?.textContent?.trim() || '';
        var opt = document.createElement('option');
        opt.value = id;
        opt.textContent = placa + (conductor ? ' | ' + conductor : '');
        mmrTeamSelect.appendChild(opt);
      });
    }
    if (mmrAsignar) mmrAsignar.removeAttribute('hidden');
    if (mmrFinalizar) mmrFinalizar.setAttribute('hidden', '');

    var detailBase = '/dashboard/servicios/';
    var _next = '?next=/dashboard/pizarra/';
    if (mmrVer)    mmrVer.href    = svId ? detailBase + svId + '/' + _next        : '#';
    if (mmrEditar) mmrEditar.href = svId ? detailBase + svId + '/editar/' + _next : '#';
    if (mmrCancelar) mmrCancelar.setAttribute('data-ps-id', psId);

    openModal('modal-menu-reserva');
  }

  // close handler — hide asignar section, show finalizar
  var mmrModal = document.getElementById('modal-menu-reserva');
  function _resetUnassignedModal() {
    if (mmrAsignar) mmrAsignar.setAttribute('hidden', '');
    if (mmrFinalizar) mmrFinalizar.removeAttribute('hidden');
    _mmrUnassignedPsId = null;
    _mmrUnassignedSvId = null;
    _mmrUnassignedFecha = '';
    _mmrUnassignedHora = '';
    if (mmrTeamSelect) { mmrTeamSelect.disabled = false; mmrTeamSelect.value = ''; }
  }
  document.querySelector('[data-close="modal-menu-reserva"]')?.addEventListener('click', function () {
    _resetUnassignedModal();
  });
  if (mmrModal) {
    mmrModal.addEventListener('click', function (e) {
      if (e.target === mmrModal) _resetUnassignedModal();
    });
  }

  // team select → assign
  var _mmrUnassignedFecha = '';
  var _mmrUnassignedHora = '';
  if (mmrTeamSelect) {
    mmrTeamSelect.addEventListener('change', function () {
      var equipoId = this.value;
      if (!equipoId) { this.value = ''; return; }
      if (!_mmrUnassignedPsId && !_mmrUnassignedSvId) { this.value = ''; return; }
      this.disabled = true;
      var p;
      if (_mmrUnassignedPsId) {
        p = moveProgramacion(_mmrUnassignedPsId, equipoId, _mmrUnassignedFecha, _mmrUnassignedHora, 'Reserva asignada al equipo');
      } else {
        p = assignServicio(_mmrUnassignedSvId, equipoId);
      }
      p.then(function (ok) {
        if (!ok) { mmrTeamSelect.disabled = false; mmrTeamSelect.value = ''; }
      });
    });
  }

  // ── MODAL: MENÚ RÁPIDO RESERVA ────────────────────────────────
  var mmrTitle     = document.getElementById('mmr-title');
  var mmrInfo      = document.getElementById('mmr-info');
  var mmrVer       = document.getElementById('mmr-ver');
  var mmrEditar    = document.getElementById('mmr-editar');
  var mmrFinalizar = document.getElementById('mmr-finalizar');
  var mmrCancelar  = document.getElementById('mmr-cancelar');

  function openMenuReserva(block) {
    var psId      = block.getAttribute('data-ps-id');
    var svPk      = block.getAttribute('data-servicio-pk');
    var codigo    = block.getAttribute('data-servicio-codigo') || '—';
    var cliente   = block.getAttribute('data-cliente')          || '—';
    var estado    = block.getAttribute('data-estado-label')     || '—';
    var hora      = block.getAttribute('data-hora')             || '—';
    var horaFin   = block.getAttribute('data-hora-fin')         || '';
    var precio    = block.getAttribute('data-precio')           || '';
    var origen    = block.getAttribute('data-origen')           || '—';
    var destino   = block.getAttribute('data-destino')          || '—';
    var durHs     = parseFloat(block.getAttribute('data-duracion-hs') || '0');
    var durLabel  = durHs > 0 ? (durHs === Math.floor(durHs) ? durHs + 'h' : durHs + 'h') : '';

    if (mmrTitle) mmrTitle.textContent = codigo + ' — ' + cliente;
    if (mmrInfo) {
      mmrInfo.innerHTML =
        '<strong>' + _esc(cliente) + '</strong><br>' +
        '<span style="color:#64748b;">' + _esc(estado) + '&nbsp;·&nbsp;' + _esc(hora) +
        (horaFin ? ' – ' + _esc(horaFin) : '') +
        (durLabel ? '&nbsp;·&nbsp;<span class="mdi mdi-clock-outline"></span>&nbsp;' + _esc(durLabel) : '') +
        '</span><br>' +
        (precio ? '<span style="font-weight:700;">' + _esc(precio) + '</span><br>' : '') +
        '<span style="font-size:12px;color:#64748b;">' + _esc(origen) + ' → ' + _esc(destino) + '</span>';
    }

    var detailBase = '/dashboard/servicios/';
    var _next = '?next=/dashboard/pizarra/';
    if (mmrVer)       mmrVer.href    = svPk ? detailBase + svPk + '/' + _next        : '#';
    if (mmrEditar)    mmrEditar.href = svPk ? detailBase + svPk + '/editar/' + _next : '#';
    if (mmrFinalizar) mmrFinalizar.setAttribute('data-ps-id', psId);
    if (mmrCancelar)  mmrCancelar.setAttribute('data-ps-id', psId);

    openModal('modal-menu-reserva');
  }

  function cambiarEstado(psId, estado) {
    ajax(ESTADO_API, { pk: parseInt(psId), estado: estado })
      .then(function (res) {
        if (res.ok) {
          closeModal('modal-menu-reserva');
          showSnack('Estado actualizado', 'ok');
          setTimeout(function () { window.location.reload(); }, 600);
        } else {
          showSnack(res.data.error || 'Error', 'error');
        }
      })
      .catch(function () { showSnack('Error de red', 'error'); });
  }

  if (mmrFinalizar) {
    mmrFinalizar.addEventListener('click', function () {
      var psId = this.getAttribute('data-ps-id');
      if (psId && confirm('¿Finalizar esta reserva?')) cambiarEstado(psId, 'finalizado');
    });
  }
  if (mmrCancelar) {
    mmrCancelar.addEventListener('click', function () {
      var psId = this.getAttribute('data-ps-id');
      if (psId && confirm('¿Cancelar esta reserva?')) cambiarEstado(psId, 'cancelado');
    });
  }

  function _to24h(str) {
    var m = (str || '').trim().match(/^(\d+):(\d+)\s*(am|pm)$/i);
    if (!m) return '';
    var h = parseInt(m[1]), mn = m[2], ap = m[3].toLowerCase();
    if (ap === 'am' && h === 12) h = 0;
    if (ap === 'pm' && h !== 12) h += 12;
    return ('0' + h).slice(-2) + ':' + mn;
  }

  // ── EVENT DELEGATION (toda la tabla) ─────────────────────────
  var pizarraTable = document.getElementById('pizarra-table');
  if (pizarraTable) {
    pizarraTable.addEventListener('click', function (e) {
      if (_rzJustDone) { _rzJustDone = false; return; }
      // Half-slot dentro de celda vacía → Nueva Reserva
      var halfSlot = e.target.closest('.td-half-slot');
      if (halfSlot) {
        var tdEmpty = halfSlot.closest('.td-empty');
        if (!tdEmpty) return;
        var fecha    = tdEmpty.getAttribute('data-fecha');
        var hora     = halfSlot.getAttribute('data-hora');
        var equipoId = tdEmpty.getAttribute('data-equipo-id');
        var thEl     = document.querySelector('.th-equipo[data-equipo-id="' + equipoId + '"]');
        var placa    = thEl ? (thEl.querySelector('.eq-placa')?.textContent.trim() || 'Equipo') : 'Equipo';
        openReservaModal(fecha, hora, equipoId, placa);
        return;
      }

      // Celda vacía (clic directo fuera de half-slot) → Nueva Reserva
      var tdEmpty = e.target.closest('.td-empty');
      if (tdEmpty) {
        var fecha    = tdEmpty.getAttribute('data-fecha');
        var equipoId = tdEmpty.getAttribute('data-equipo-id');
        var thEl     = document.querySelector('.th-equipo[data-equipo-id="' + equipoId + '"]');
        var placa    = thEl ? (thEl.querySelector('.eq-placa')?.textContent.trim() || 'Equipo') : 'Equipo';
        // Default to this slot's time.
        var firstHalf = tdEmpty.querySelector('.td-half-slot');
        var hora = tdEmpty.getAttribute('data-hora')
          || (firstHalf ? firstHalf.getAttribute('data-hora') : '');
        openReservaModal(fecha, hora, equipoId, placa);
        return;
      }

      // Botón "+" → Crear Equipo
      var btnAdd = e.target.closest('.btn-add-equipo');
      if (btnAdd) {
        openEquipoModal(btnAdd.getAttribute('data-fecha-iso'));
        return;
      }

      // Bloque de reserva → Menú rápido
      var block = e.target.closest('.booking-block');
      if (block && !block.classList.contains('dragging')) {
        openMenuReserva(block);
        return;
      }

      var btnEditEquipo = e.target.closest('.btn-edit-equipo');
      if (btnEditEquipo) {
        openEquipoEditModal(parseInt(btnEditEquipo.dataset.equipoId));
        return;
      }

      // Botón X → Eliminar / Desasignar Equipo
      var btnDel = e.target.closest('.btn-del-equipo');
      if (btnDel) {
        var th = btnDel.closest('.th-equipo');
        if (!th) return;
        var eqId       = th.getAttribute('data-equipo-id');
        var nServicios = parseInt(th.getAttribute('data-n-servicios') || '0');
        var msg = nServicios > 0
          ? '¿Desasignar equipo? Las ' + nServicios + ' reserva(s) quedarán sin equipo asignado.'
          : '¿Eliminar este equipo? Esta acción no se puede deshacer.';
        if (!confirm(msg)) return;
        ajax(AJAX_BASE + 'equipo/eliminar/', { equipo_id: parseInt(eqId) })
          .then(function (res) {
            if (res.ok) {
              showSnack(nServicios > 0 ? 'Equipo desasignado' : 'Equipo eliminado', 'ok');
              setTimeout(function () { window.location.reload(); }, 600);
            } else {
              showSnack(res.data.error || 'Error al eliminar', 'error');
            }
          })
          .catch(function () { showSnack('Error de red', 'error'); });
        return;
      }
    });
  }

  // ── ORPHAN DRAG ITEMS ────────────────────────────────────────
  document.querySelectorAll('.orphan-item[draggable]').forEach(function (item) {
    item.addEventListener('dragstart', function (e) {
      draggedPsId         = this.getAttribute('data-ps-id');
      draggedBlock        = null;
      draggedIsUnassigned = true;
      draggedOriginalHour = '';
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', draggedPsId);
      setTimeout(function () { item.classList.add('dragging'); }, 0);
    });
    item.addEventListener('dragend', function () {
      item.classList.remove('dragging');
      draggedPsId  = null;
      draggedBlock = null;
      document.querySelectorAll('.drag-over, .drag-over-conflict').forEach(function (td) {
        td.classList.remove('drag-over', 'drag-over-conflict');
      });
    });
  });

  // ── DRAG & DROP ───────────────────────────────────────────────
  var draggedPsId = null;
  var draggedSvId = null;
  var draggedBlock = null;
  var draggedIsUnassigned = false;
  var draggedOriginalHour = '';
  var _hoveredHalfSlot = null;

  var _dropIndicator = null;

  function _clearDropIndicator() {
    if (_dropIndicator) { _dropIndicator.remove(); _dropIndicator = null; }
  }

  function _getSubSlotHora(bookingCell, clientX) {
    var block = bookingCell.querySelector('.booking-block');
    if (!block) return null;
    var ini24 = _to24h ? _to24h(block.getAttribute('data-hora') || '') : (block.getAttribute('data-hora') || '');
    if (!ini24) return null;
    var span  = parseInt(bookingCell.getAttribute('colspan')) || 1;
    var rect  = bookingCell.getBoundingClientRect();
    var sub   = Math.max(0, Math.min(span - 1, Math.floor((clientX - rect.left) / (rect.width / span))));
    return _addMin24 ? _addMin24(ini24, sub * 30) : ini24;
  }

  function _updateDropIndicator(bookingCell, clientX) {
    var hora = _getSubSlotHora(bookingCell, clientX);
    if (!hora) { _clearDropIndicator(); return; }
    if (!_dropIndicator) {
      _dropIndicator = document.createElement('div');
      _dropIndicator.className = 'drop-indicator';
      var lbl = document.createElement('span');
      lbl.className = 'drop-indicator-label';
      _dropIndicator.appendChild(lbl);
      document.body.appendChild(_dropIndicator);
    }
    var span = parseInt(bookingCell.getAttribute('colspan')) || 1;
    var rect = bookingCell.getBoundingClientRect();
    var sw   = rect.width / span;
    var sub  = Math.max(0, Math.min(span - 1, Math.floor((clientX - rect.left) / sw)));
    var ix   = rect.left + sub * sw;
    _dropIndicator.style.top    = rect.top + 'px';
    _dropIndicator.style.left   = ix + 'px';
    _dropIndicator.style.height = rect.height + 'px';
    _dropIndicator.querySelector('.drop-indicator-label').textContent = hora;
  }

  function clearDragState() {
    if (draggedBlock) draggedBlock.classList.remove('dragging');
    draggedPsId = null;
    draggedSvId = null;
    draggedBlock = null;
    draggedIsUnassigned = false;
    draggedOriginalHour = '';
    _hoveredHalfSlot = null;
    _clearDropIndicator();
    document.querySelectorAll('.drag-over, .drag-over-conflict').forEach(function (el) {
      el.classList.remove('drag-over', 'drag-over-conflict');
    });
  }

  function moveProgramacion(psId, equipoId, fecha, hora, successMessage) {
    if (!psId || !equipoId || !fecha || !hora) return Promise.resolve(false);
    return ajax(AJAX_BASE + 'programacion/mover/', {
      ps_id: parseInt(psId),
      equipo_id: parseInt(equipoId),
      fecha: fecha,
      hora: hora,
    }).then(function (res) {
      if (res.ok) {
        showSnack(successMessage || 'Reserva asignada', 'ok');
        setTimeout(function () { window.location.reload(); }, 500);
        return true;
      }
      showSnack(res.data.error || 'Error al asignar', 'error');
      return false;
    }).catch(function () {
      showSnack('Error de red', 'error');
      return false;
    });
  }

  function assignServicio(servicioId, equipoId) {
    if (!servicioId || !equipoId) return Promise.resolve(false);
    return ajax(AJAX_BASE + 'programacion/asignar/', {
      servicio_id: parseInt(servicioId),
      equipo_id: parseInt(equipoId),
    }).then(function (res) {
      if (res.ok) {
        showSnack('Reserva asignada al equipo', 'ok');
        setTimeout(function () { window.location.reload(); }, 300);
        return true;
      }
      showSnack(res.data.error || 'Error al asignar', 'error');
      return false;
    }).catch(function () {
      showSnack('Error de red', 'error');
      return false;
    });
  }

  if (pizarraTable) {
    pizarraTable.addEventListener('click', function (e) {
      var card = e.target.closest('.unassigned-card');
      if (card) {
        openUnassignedMenu(card);
        return;
      }
    });

    pizarraTable.addEventListener('dragstart', function (e) {
      if (_rzState) { e.preventDefault(); return; }
      var source = e.target.closest('.booking-block[draggable="true"], .unassigned-card[draggable="true"]');
      if (!source) return;
      draggedPsId = source.getAttribute('data-ps-id') || null;
      draggedSvId = source.getAttribute('data-servicio-id') || null;
      draggedBlock = source;
      draggedIsUnassigned = source.classList.contains('unassigned-card');
      draggedOriginalHour = source.getAttribute('data-hora') || '';
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', draggedPsId);
      setTimeout(function () {
        if (draggedBlock) draggedBlock.classList.add('dragging');
      }, 0);
    });

    pizarraTable.addEventListener('dragend', clearDragState);

    pizarraTable.addEventListener('dragover', function (e) {
      if (!draggedPsId && !draggedSvId) return;
      var halfSlot    = e.target.closest('.td-half-slot');
      var emptyCell   = e.target.closest('.td-empty');
      var bookingCell = !draggedIsUnassigned ? e.target.closest('.td-booking') : null;
      var teamRow     = e.target.closest('.matrix-team-row');
      if (emptyCell) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        _clearDropIndicator();
        var hs = halfSlot || emptyCell.querySelector('.td-half-slot');
        if (hs && _hoveredHalfSlot !== hs) {
          if (_hoveredHalfSlot) _hoveredHalfSlot.classList.remove('drag-over', 'drag-over-conflict');
          _hoveredHalfSlot = hs;
          hs.classList.add('drag-over');
        }
      } else if (bookingCell) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (_hoveredHalfSlot) { _hoveredHalfSlot.classList.remove('drag-over', 'drag-over-conflict'); _hoveredHalfSlot = null; }
        _updateDropIndicator(bookingCell, e.clientX);
      } else if (draggedIsUnassigned && teamRow) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (_hoveredHalfSlot) { _hoveredHalfSlot.classList.remove('drag-over', 'drag-over-conflict'); _hoveredHalfSlot = null; }
        _clearDropIndicator();
        teamRow.classList.add('drag-over');
      } else {
        if (_hoveredHalfSlot) { _hoveredHalfSlot.classList.remove('drag-over', 'drag-over-conflict'); _hoveredHalfSlot = null; }
        _clearDropIndicator();
      }
    });

    pizarraTable.addEventListener('dragleave', function (e) {
      var halfSlot = e.target.closest('.td-half-slot');
      if (halfSlot && !halfSlot.contains(e.relatedTarget)) {
        halfSlot.classList.remove('drag-over', 'drag-over-conflict');
        if (_hoveredHalfSlot === halfSlot) _hoveredHalfSlot = null;
        return;
      }
      var bookingCell = e.target.closest('.td-booking');
      if (bookingCell && !bookingCell.contains(e.relatedTarget)) {
        _clearDropIndicator();
        return;
      }
      var teamRow = e.target.closest('.matrix-team-row');
      if (teamRow && !e.target.closest('.td-half-slot') && !teamRow.contains(e.relatedTarget)) {
        teamRow.classList.remove('drag-over', 'drag-over-conflict');
      }
    });

    pizarraTable.addEventListener('drop', function (e) {
      if (!draggedPsId && !draggedSvId) return;
      var halfSlot    = e.target.closest('.td-half-slot');
      var emptyCell   = e.target.closest('.td-empty');
      var bookingCell = !draggedIsUnassigned ? e.target.closest('.td-booking') : null;
      var teamRow     = e.target.closest('.matrix-team-row');

      var dropTarget = emptyCell || (!draggedIsUnassigned && bookingCell ? bookingCell : null) || (draggedIsUnassigned ? teamRow : null);
      if (!dropTarget) return;
      e.preventDefault();

      var equipoId = dropTarget.getAttribute('data-equipo-id');
      var fecha    = dropTarget.getAttribute('data-fecha');
      if ((!equipoId || !fecha) && teamRow) {
        equipoId = teamRow.getAttribute('data-equipo-id');
        fecha    = teamRow.getAttribute('data-fecha');
      }

      var hora = '';
      if (emptyCell) {
        var slot = halfSlot || (_hoveredHalfSlot && _hoveredHalfSlot.closest('.td-empty') === emptyCell ? _hoveredHalfSlot : null) || emptyCell.querySelector('.td-half-slot');
        if (slot) hora = slot.getAttribute('data-hora') || '';
      } else if (bookingCell) {
        hora = _getSubSlotHora(bookingCell, e.clientX) || '';
        var tr = bookingCell.closest('.matrix-team-row');
        if (tr) { equipoId = equipoId || tr.getAttribute('data-equipo-id'); fecha = fecha || tr.getAttribute('data-fecha'); }
      } else {
        hora = draggedOriginalHour;
      }

      if (_hoveredHalfSlot) { _hoveredHalfSlot.classList.remove('drag-over', 'drag-over-conflict'); _hoveredHalfSlot = null; }
      _clearDropIndicator();
      dropTarget.classList.remove('drag-over', 'drag-over-conflict');
      if (draggedPsId) {
        moveProgramacion(
          draggedPsId,
          equipoId,
          fecha,
          hora,
          draggedIsUnassigned ? 'Reserva asignada al equipo' : 'Reserva movida'
        );
      } else {
        assignServicio(draggedSvId, equipoId);
      }
    });
  }

  // ── RESIZE DE DURACIÓN POR ARRASTRE ──────────────────────────
  var _rzState    = null;
  var _rzJustDone = false;

  function _addMin24(t24, mins) {
    var parts = t24.split(':');
    var total = parseInt(parts[0]) * 60 + parseInt(parts[1]) + mins;
    if (total < 0) total = 0;
    if (total > 1439) total = 1439;
    return ('0' + Math.floor(total / 60)).slice(-2) + ':' + ('0' + (total % 60)).slice(-2);
  }

  function _buildSlotPositions() {
    var map = {};
    pizarraTable.querySelectorAll('.td-half-slot[data-hora]').forEach(function(el) {
      var hora = el.getAttribute('data-hora');
      if (!map[hora]) {
        var r = el.getBoundingClientRect();
        if (r.width > 0) map[hora] = { hora: hora, left: r.left, right: r.right };
      }
    });
    pizarraTable.querySelectorAll('th.matrix-hour[data-hora]').forEach(function(th) {
      var hora = th.getAttribute('data-hora');
      var r = th.getBoundingClientRect();
      if (r.width <= 0) return;
      var mid = r.left + r.width / 2;
      if (!map[hora])                map[hora]               = { hora: hora,               left: r.left, right: mid     };
      if (!map[_addMin24(hora, 30)]) map[_addMin24(hora, 30)] = { hora: _addMin24(hora, 30), left: mid,    right: r.right };
    });
    return Object.values(map).sort(function(a, b) { return a.left - b.left; });
  }

  pizarraTable.addEventListener('mousedown', function(e) {
    var btn = e.target.closest('.bb-btn-duracion');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var block = btn.closest('.booking-block');
    if (!block) return;

    // Desactivar draggable en el bloque para que el browser no inicie D&D
    block.removeAttribute('draggable');
    var restoreDraggable = function() {
      block.setAttribute('draggable', 'true');
      document.removeEventListener('mouseup', restoreDraggable);
    };
    document.addEventListener('mouseup', restoreDraggable);

    var psId    = block.getAttribute('data-ps-id');
    var horaIni = block.getAttribute('data-hora') || '';
    var ini24   = _to24h(horaIni);
    var br      = block.getBoundingClientRect();
    var ghost   = document.createElement('div');
    ghost.className = 'rz-ghost';
    ghost.style.cssText = 'position:fixed;top:' + br.top + 'px;left:' + br.left + 'px;height:' + br.height + 'px;width:' + br.width + 'px;pointer-events:none;z-index:500;';
    document.body.style.cursor = 'ew-resize';
    document.body.appendChild(ghost);
    var tip = document.createElement('div');
    tip.className = 'rz-tooltip';
    tip.style.cssText = 'position:fixed;z-index:501;pointer-events:none;display:none;';
    document.body.appendChild(tip);
    _rzState = { psId: psId, ini24: ini24, blockLeft: br.left, ghost: ghost, tip: tip, slotMap: _buildSlotPositions(), targetFin: null };
  });

  document.addEventListener('mousemove', function(e) {
    if (!_rzState) return;
    var st = _rzState, mx = e.clientX, horaSlot = null;
    for (var i = 0; i < st.slotMap.length; i++) {
      if (mx >= st.slotMap[i].left && mx < st.slotMap[i].right) { horaSlot = st.slotMap[i].hora; break; }
    }
    var fin24 = horaSlot ? _addMin24(horaSlot, 30) : null;
    if (fin24 && fin24 <= st.ini24) fin24 = null;
    st.targetFin = fin24;
    st.ghost.style.width = Math.max(mx - st.blockLeft, 40) + 'px';
    if (fin24) {
      st.tip.textContent = '→ ' + fin24;
      st.tip.style.display = 'block';
      st.tip.style.left = (mx + 12) + 'px';
      st.tip.style.top  = (e.clientY - 28) + 'px';
    } else {
      st.tip.style.display = 'none';
    }
  });

  document.addEventListener('mouseup', function() {
    if (!_rzState) return;
    var st = _rzState;
    _rzState = null;
    document.body.style.cursor = '';
    st.ghost.remove();
    st.tip.remove();
    _rzJustDone = true;
    setTimeout(function() { _rzJustDone = false; }, 0);
    if (!st.targetFin || !st.psId) return;
    ajax(DURACION_API, { ps_id: parseInt(st.psId), hora_fin: st.targetFin })
      .then(function(res) {
        if (res.ok) { showSnack('Duración actualizada', 'ok'); setTimeout(function() { window.location.reload(); }, 600); }
        else showSnack(res.data.error || 'Error', 'error');
      })
      .catch(function() { showSnack('Error de red', 'error'); });
  });

  // ── CLICK-DRAG SCROLL HORIZONTAL ─────────────────────────────
  var matrixScroll = document.querySelector('.pizarra-matrix-scroll');
  if (matrixScroll) {
    var _scrolling = false;
    var _scrollStartX = 0;
    var _scrollLeft0  = 0;

    matrixScroll.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      if (e.target.closest('.booking-block[draggable="true"], .unassigned-card[draggable="true"], button, a, input, select')) return;
      _scrolling  = true;
      _scrollStartX = e.clientX;
      _scrollLeft0  = matrixScroll.scrollLeft;
      matrixScroll.style.cursor = 'grabbing';
      matrixScroll.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', function (e) {
      if (!_scrolling) return;
      matrixScroll.scrollLeft = _scrollLeft0 - (e.clientX - _scrollStartX);
    });

    document.addEventListener('mouseup', function () {
      if (!_scrolling) return;
      _scrolling = false;
      matrixScroll.style.cursor = '';
      matrixScroll.style.userSelect = '';
    });
  }

})();
