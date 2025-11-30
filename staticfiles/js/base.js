/**
 * ProyectoKasu - Sistema de Gestión de Transporte
 * JavaScript Base
 */

// Esperar a que el DOM esté completamente cargado
document.addEventListener('DOMContentLoaded', function() {
    
    // ========================================================================
    // Auto-cerrar mensajes de alerta después de 5 segundos
    // ========================================================================
    const alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
        alerts.forEach(function(alert) {
            setTimeout(function() {
                alert.style.transition = 'opacity 0.5s ease';
                alert.style.opacity = '0';
                setTimeout(function() {
                    alert.remove();
                }, 500);
            }, 5000);
        });
    }

    // ========================================================================
    // Navegación activa - resaltar página actual
    // ========================================================================
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(function(link) {
        if (link.getAttribute('href') === currentPath) {
            link.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
            link.style.borderBottom = '2px solid #F39C12';
        }
    });

    // ========================================================================
    // Confirmación de eliminación
    // ========================================================================
    const deleteButtons = document.querySelectorAll('[data-confirm-delete]');
    if (deleteButtons.length > 0) {
        deleteButtons.forEach(function(button) {
            button.addEventListener('click', function(e) {
                const message = this.getAttribute('data-confirm-delete') || 
                               '¿Está seguro de que desea eliminar este elemento?';
                if (!confirm(message)) {
                    e.preventDefault();
                    return false;
                }
            });
        });
    }

    // ========================================================================
    // Toggle móvil para navegación (Menú hamburguesa)
    // ========================================================================
    const navToggle = document.getElementById('navbarToggle');
    const navMenu = document.getElementById('navbarMenu');
    const navOverlay = document.getElementById('navbarOverlay');
    
    if (navToggle && navMenu) {
        // Función para abrir el menú
        const openMenu = function() {
            navMenu.classList.add('active');
            navToggle.classList.add('active');
            if (navOverlay) navOverlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        };
        
        // Función para cerrar el menú
        const closeMenu = function() {
            navMenu.classList.remove('active');
            navToggle.classList.remove('active');
            if (navOverlay) navOverlay.classList.remove('active');
            document.body.style.overflow = '';
        };
        
        // Toggle del menú al hacer clic en el botón hamburguesa
        navToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            if (navMenu.classList.contains('active')) {
                closeMenu();
            } else {
                openMenu();
            }
        });
        
        // Cerrar menú al hacer clic en un enlace
        const navLinks = navMenu.querySelectorAll('.nav-link');
        navLinks.forEach(function(link) {
            link.addEventListener('click', function() {
                closeMenu();
            });
        });
        
        // Cerrar menú al hacer clic en el overlay
        if (navOverlay) {
            navOverlay.addEventListener('click', function() {
                closeMenu();
            });
        }
        
        // Cerrar menú al presionar la tecla ESC
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && navMenu.classList.contains('active')) {
                closeMenu();
            }
        });
        
        // Cerrar menú al cambiar de tamaño de ventana (de móvil a escritorio)
        const mediaQuery = window.matchMedia('(max-width: 992px)');
        window.addEventListener('resize', function() {
            if (!mediaQuery.matches && navMenu.classList.contains('active')) {
                closeMenu();
            }
        });
    }

    // ========================================================================
    // Scroll suave para anclas
    // ========================================================================
    const smoothScrollLinks = document.querySelectorAll('a[href^="#"]');
    smoothScrollLinks.forEach(function(link) {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href !== '#' && href !== '#!') {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });

    // ========================================================================
    // Validación de formularios (básica)
    // ========================================================================
    const forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;

            requiredFields.forEach(function(field) {
                if (!field.value.trim()) {
                    isValid = false;
                    field.style.borderColor = '#E74C3C';
                } else {
                    field.style.borderColor = '#BDC3C7';
                }
            });

            if (!isValid) {
                e.preventDefault();
                alert('Por favor complete todos los campos obligatorios.');
                return false;
            }
        });
    });

    // ========================================================================
    // Tooltips simples
    // ========================================================================
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(function(element) {
        element.addEventListener('mouseenter', function() {
            const tooltipText = this.getAttribute('data-tooltip');
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = tooltipText;
            tooltip.style.cssText = `
                position: absolute;
                background-color: #2C3E50;
                color: white;
                padding: 0.5rem 1rem;
                border-radius: 4px;
                font-size: 0.875rem;
                z-index: 1000;
                white-space: nowrap;
            `;
            
            document.body.appendChild(tooltip);
            
            const rect = this.getBoundingClientRect();
            tooltip.style.top = (rect.top - tooltip.offsetHeight - 10) + 'px';
            tooltip.style.left = (rect.left + (rect.width - tooltip.offsetWidth) / 2) + 'px';
            
            this.tooltipElement = tooltip;
        });

        element.addEventListener('mouseleave', function() {
            if (this.tooltipElement) {
                this.tooltipElement.remove();
                this.tooltipElement = null;
            }
        });
    });

    // ========================================================================
    // Mostrar/Ocultar contraseña
    // ========================================================================
    const passwordToggles = document.querySelectorAll('[data-toggle-password]');
    passwordToggles.forEach(function(toggle) {
        toggle.addEventListener('click', function() {
            const targetId = this.getAttribute('data-toggle-password');
            const passwordField = document.getElementById(targetId);
            
            if (passwordField) {
                if (passwordField.type === 'password') {
                    passwordField.type = 'text';
                    this.textContent = '🙈';
                } else {
                    passwordField.type = 'password';
                    this.textContent = '👁️';
                }
            }
        });
    });

    // ========================================================================
    // Logging de eventos (para desarrollo)
    // ========================================================================
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        console.log('🚛 ProyectoKasu - Sistema de Gestión de Transporte');
        console.log('📍 Página cargada:', currentPath);
    }

});

// ========================================================================
// Utilidades globales
// ========================================================================

/**
 * Formatea números como moneda mexicana
 * @param {number} amount 
 * @returns {string}
 */
function formatMXN(amount) {
    return new Intl.NumberFormat('es-MX', {
        style: 'currency',
        currency: 'MXN'
    }).format(amount);
}

/**
 * Formatea fechas en formato mexicano
 * @param {Date|string} date 
 * @returns {string}
 */
function formatDate(date) {
    const d = new Date(date);
    return new Intl.DateTimeFormat('es-MX', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    }).format(d);
}

/**
 * Muestra una notificación temporal
 * @param {string} message 
 * @param {string} type - success, error, warning, info
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.innerHTML = `
        <span class="alert-icon">
            ${type === 'success' ? '✓' : type === 'error' ? '✗' : type === 'warning' ? '⚠' : 'ℹ'}
        </span>
        <span class="alert-message">${message}</span>
    `;
    
    const container = document.querySelector('.messages-container .container') || 
                     document.querySelector('.container');
    
    if (container) {
        container.insertBefore(notification, container.firstChild);
        
        setTimeout(function() {
            notification.style.transition = 'opacity 0.5s ease';
            notification.style.opacity = '0';
            setTimeout(function() {
                notification.remove();
            }, 500);
        }, 5000);
    }
}

// Exportar funciones para uso global
window.formatMXN = formatMXN;
window.formatDate = formatDate;
window.showNotification = showNotification;
