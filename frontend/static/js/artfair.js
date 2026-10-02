/**
 * ARTFAIR - Frontend Application Controller
 * Handles Session Auth, Real-time Gallery Filtering, CSRF, and Modals.
 */

(function () {
  'use strict';

  // Global State
  const state = {
    csrfToken: '',
    currentUser: null,
    favoriteIds: new Set(),
    notifications: [],
    unreadNotificationCount: 0,
    filters: {
      page: 1,
      category: '',
      tag: '',
      style: '',
      license_type: '',
      min_price: '',
      max_price: '',
      search: '',
      ordering: '-created_at'
    },
    categories: [],
    tags: []
  };

  // Auth Token Storage (cross-origin / 3rd-party cookie immune)
  function getAuthToken() {
    try {
      return sessionStorage.getItem('artfair_auth_token') || localStorage.getItem('artfair_auth_token') || '';
    } catch (_) {
      return '';
    }
  }

  function setAuthToken(token) {
    try {
      if (token) {
        sessionStorage.setItem('artfair_auth_token', token);
        localStorage.setItem('artfair_auth_token', token);
      } else {
        sessionStorage.removeItem('artfair_auth_token');
        localStorage.removeItem('artfair_auth_token');
      }
    } catch (_) {}
  }

  // Utility: Get CSRF token from document cookies
  function getCookie(name) {
    if (!document.cookie) return null;
    const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  // Live CSRF Token Resolver: Always checks document.cookie first because Django rotates cookie on login/logout
  function getCsrfToken() {
    const cookieToken = getCookie('csrftoken');
    if (cookieToken) {
      state.csrfToken = cookieToken;
      const meta = document.querySelector('meta[name="csrf-token"]');
      if (meta && meta.content !== cookieToken) meta.content = cookieToken;
      return cookieToken;
    }
    if (state.csrfToken) return state.csrfToken;
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      state.csrfToken = meta.content;
      return meta.content;
    }
    return '';
  }

  function syncCsrfToken(newToken) {
    if (newToken) {
      state.csrfToken = newToken;
      const meta = document.querySelector('meta[name="csrf-token"]');
      if (meta) meta.content = newToken;
    } else {
      getCsrfToken();
    }
  }

  async function fetchCsrfToken() {
    try {
      const csrfUrl = (window.ArtFairConfig && window.ArtFairConfig.apiUrl)
        ? window.ArtFairConfig.apiUrl('/api/accounts/auth/csrf/')
        : '/api/accounts/auth/csrf/';
      const res = await fetch(csrfUrl, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        if (data.csrf_token) {
          syncCsrfToken(data.csrf_token);
        }
      }
    } catch (_) {}
    return getCsrfToken();
  }

  // Centralized API Request Wrapper with CSRF protection, Token Auth, and Base URL resolution
  async function apiFetch(url, options = {}) {
    const resolvedUrl = (window.ArtFairConfig && window.ArtFairConfig.apiUrl)
      ? window.ArtFairConfig.apiUrl(url)
      : url;

    const method = (options.method || 'GET').toUpperCase();
    const headers = Object.assign({}, options.headers || {});

    // Check if endpoint is an unauthenticated public auth endpoint
    const isPublicAuthEndpoint = url.includes('/api/accounts/auth/login') ||
                                 url.includes('/api/accounts/auth/register') ||
                                 url.includes('/api/accounts/auth/csrf');

    // Attach Token Authorization header if user has authenticated token (NEVER on login, register, or csrf)
    const token = getAuthToken();
    if (token && !headers['Authorization'] && !isPublicAuthEndpoint) {
      headers['Authorization'] = `Token ${token}`;
    }

    // Attach CSRF Token for mutating requests if available
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const csrf = getCsrfToken();
      if (csrf && !headers['X-CSRFToken']) {
        headers['X-CSRFToken'] = csrf;
      }
    }

    const fetchOptions = {
      ...options,
      method,
      headers,
      credentials: options.credentials || 'include'
    };

    try {
      const res = await fetch(resolvedUrl, fetchOptions);

      // Check for Invalid Token failure (401 Unauthorized)
      if (res.status === 401) {
        const clone = res.clone();
        try {
          const bodyText = await clone.text();
          if (bodyText.includes('Invalid token') || bodyText.includes('invalid_token')) {
            console.warn('[ARTFAIR Auth] Stale or invalid token detected. Purging invalid token from storage...');
            setAuthToken('');
            state.currentUser = null;
            renderNavbarAuth();
            window.dispatchEvent(new CustomEvent('artfair:user_loaded', { detail: null }));
          }
        } catch (_) {}
      }

      // Check for CSRF failure
      if (res.status === 403) {
        const clone = res.clone();
        try {
          const bodyText = await clone.text();
          if (bodyText.includes('CSRF') || bodyText.includes('Csrftoken') || bodyText.includes('csrf')) {
            console.warn('[ARTFAIR CSRF Mismatch] Request to', resolvedUrl, 'failed CSRF check. Re-syncing token...');
            await fetchCsrfToken();
            showToast('Phiên xác thực đã thay đổi. Vui lòng tải lại trang và thử lại.', 'error');
          }
        } catch (_) {}
      }

      return res;
    } catch (err) {
      throw err;
    }
  }

  // Utility: Toast notifications
  function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let iconSvg = '';
    if (type === 'success') {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#28A745" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (type === 'error') {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#DC3545" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
    } else {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C52A70" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
    }

    toast.innerHTML = `${iconSvg}<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(40px)';
      setTimeout(() => toast.remove(), 300);
    }, 3800);
  }

  // Public helper to show notice about upcoming features & global helpers
  window.ArtFair = {
    state: state,
    getCsrfToken: getCsrfToken,
    syncCsrfToken: syncCsrfToken,
    fetchCsrfToken: fetchCsrfToken,
    getAuthToken: getAuthToken,
    setAuthToken: setAuthToken,
    apiFetch: apiFetch,
    showToast: showToast,
    showNotice: function(msg) {
      showToast(msg || 'Tính năng đang được phát triển trong giai đoạn kế tiếp.', 'info');
    },
    openAuthModal: function(tab = 'login') {
      openAuthModal(tab);
    },
    closeAuthModal: function() {
      closeAuthModal();
    },
    downloadOriginalArtworkFile: downloadOriginalArtworkFile,
    downloadOrderCertificate: downloadOrderCertificate,
    getCurrentUser: function() { return state.currentUser; }
  };

  // 1. Initialize CSRF token from live cookie or meta tag
  function initCsrfToken() {
    getCsrfToken();
  }

  // 2. Check current authenticated user session
  async function checkCurrentUser() {
    try {
      const res = await apiFetch('/api/accounts/me/');
      if (res.ok) {
        state.currentUser = await res.json();
        await Promise.allSettled([
          loadUserFavorites(),
          loadNotifications()
        ]);
      } else {
        state.currentUser = null;
        state.favoriteIds = new Set();
        state.notifications = [];
        state.unreadNotificationCount = 0;
      }
    } catch (err) {
      state.currentUser = null;
      state.favoriteIds = new Set();
      state.notifications = [];
      state.unreadNotificationCount = 0;
    }
    renderNavbarAuth();
    window.dispatchEvent(new CustomEvent('artfair:user_loaded', { detail: state.currentUser }));
  }

  // Notification Helpers
  async function loadNotifications() {
    try {
      const res = await apiFetch('/api/accounts/notifications/');
      if (res.ok) {
        const data = await res.json();
        state.notifications = data.results || (Array.isArray(data) ? data : []);
        state.unreadNotificationCount = state.notifications.filter(n => !n.is_read).length;
        updateNotificationBadge();
        renderNotificationDropdownItems();
      }
    } catch (e) {
      console.error('Failed to load notifications', e);
    }
  }

  function updateNotificationBadge() {
    const badge = document.getElementById('notificationBadgeCount');
    if (badge) {
      if (state.unreadNotificationCount > 0) {
        badge.textContent = state.unreadNotificationCount > 99 ? '99+' : state.unreadNotificationCount;
        badge.style.display = 'flex';
      } else {
        badge.style.display = 'none';
      }
    }
  }

  function renderNotificationDropdownItems() {
    const list = document.getElementById('notificationListItems');
    if (!list) return;
    if (state.notifications.length === 0) {
      list.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 0.85rem;">Bạn chưa có thông báo nào.</div>`;
      return;
    }
    const recent = state.notifications.slice(0, 5);
    list.innerHTML = recent.map(n => `
      <div class="notification-item ${n.is_read ? '' : 'unread'}" data-notif-id="${n.id}" style="padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); cursor: pointer; transition: background var(--trans-fast); ${n.is_read ? 'background:#FFFFFF;' : 'background:#FDF2F8;'}">
        <div style="font-weight: 700; font-size: 0.84rem; color: var(--text-plum); margin-bottom: 3px; display: flex; align-items: center; justify-content: space-between;">
          <span>${n.title}</span>
          ${!n.is_read ? '<span style="width: 7px; height: 7px; border-radius: 50%; background: #E11D48; display: inline-block;"></span>' : ''}
        </div>
        <div style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 4px;">${n.message}</div>
        <div style="font-size: 0.72rem; color: var(--text-muted); opacity: 0.8;">${new Date(n.created_at).toLocaleString('vi-VN')}</div>
      </div>
    `).join('');

    list.querySelectorAll('.notification-item').forEach(item => {
      item.addEventListener('click', async () => {
        const id = item.getAttribute('data-notif-id');
        const notif = state.notifications.find(n => n.id == id);
        if (notif && !notif.is_read) {
          await markNotificationAsRead(id);
        }
        if (notif && notif.link_url) {
          const targetUrl = (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(notif.link_url) : notif.link_url;
          window.location.href = targetUrl;
        }
      });
    });
  }

  async function markNotificationAsRead(id) {
    try {
      const res = await apiFetch(`/api/accounts/notifications/${id}/read/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      if (res.ok) {
        const notif = state.notifications.find(n => n.id == id);
        if (notif) notif.is_read = true;
        state.unreadNotificationCount = Math.max(0, state.unreadNotificationCount - 1);
        updateNotificationBadge();
        renderNotificationDropdownItems();
      }
    } catch(e) {}
  }

  async function markAllNotificationsAsRead() {
    try {
      const res = await apiFetch('/api/accounts/notifications/mark-all-read/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      if (res.ok) {
        state.notifications.forEach(n => n.is_read = true);
        state.unreadNotificationCount = 0;
        updateNotificationBadge();
        renderNotificationDropdownItems();
        showToast('Đã đánh dấu tất cả thông báo là đã đọc.', 'success');
      }
    } catch(e) {}
  }

  // Favorite Helpers
  async function loadUserFavorites() {
    try {
      const res = await apiFetch('/api/artworks/favorites/ids/');
      if (res.ok) {
        const data = await res.json();
        state.favoriteIds = new Set(data.favorite_ids || []);
      }
    } catch (e) {
      state.favoriteIds = new Set();
    }
  }

  async function toggleArtworkFavorite(artId, btnElem) {
    try {
      const res = await apiFetch(`/api/artworks/${artId}/favorite/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      if (res.ok) {
        const data = await res.json();
        const isFav = data.is_favorited;
        if (isFav) {
          state.favoriteIds.add(Number(artId));
        } else {
          state.favoriteIds.delete(Number(artId));
        }
        if (btnElem) {
          btnElem.classList.toggle('active', isFav);
          btnElem.title = isFav ? 'Bỏ lưu yêu thích' : 'Yêu thích';
          const svg = btnElem.querySelector('svg');
          if (svg) {
            svg.setAttribute('fill', isFav ? '#E11D48' : 'none');
            svg.setAttribute('stroke', isFav ? '#E11D48' : 'currentColor');
          }
        }
        showToast(data.detail, 'success');
      } else {
        const data = await res.json();
        showToast(data.detail || 'Không thể lưu tác phẩm yêu thích.', 'error');
      }
    } catch (err) {
      showToast('Lỗi kết nối khi cập nhật yêu thích.', 'error');
    }
  }

  // Scoped Image Protection
  function protectArtworkImages() {
    const images = document.querySelectorAll('.art-card-img, .showcase-main-img, .protected-artwork-img');
    images.forEach(img => {
      img.setAttribute('draggable', 'false');
      img.addEventListener('contextmenu', (e) => e.preventDefault());
      img.addEventListener('dragstart', (e) => e.preventDefault());
    });
  }

  // Render Navbar state based on login status
  function renderNavbarAuth() {
    const authContainer = document.getElementById('navbarAuthArea');
    const mobileAuthContainer = document.getElementById('mobileDrawerAuthArea');
    const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;

    if (state.currentUser) {
      const user = state.currentUser;
      const isCreator = user.role === 'CREATOR';
      const displayName = (user.artist_profile && user.artist_profile.display_name) 
        ? user.artist_profile.display_name 
        : (user.username || 'Người dùng');
      const avatarUrl = (user.artist_profile && user.artist_profile.avatar) 
        ? (window.ArtFairConfig ? window.ArtFairConfig.mediaUrl(user.artist_profile.avatar) : user.artist_profile.avatar)
        : '';
      const initial = displayName.charAt(0).toUpperCase();

      if (authContainer) {
        authContainer.innerHTML = `
          ${isCreator ? `
            <a href="${pUrl('/studio/')}" class="btn btn-secondary btn-sm" id="navBtnCreatorStudio" style="text-decoration:none; display:inline-flex; align-items:center; gap:6px; font-weight:700; color:var(--primary-berry); border-color:var(--primary-berry); padding:6px 14px; border-radius:var(--radius-full); margin-right:4px;" title="Vào Creator Studio để quản lý và đăng bán tranh">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
              <span>Creator Studio</span>
            </a>
          ` : ''}

          <!-- Notification Bell -->
          <div class="notification-bell-container" id="notificationBellContainer">
            <button type="button" class="notification-bell-btn" id="notificationBellBtn" title="Thông báo" aria-label="Xem thông báo">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
              </svg>
              <span class="notification-badge-count" id="notificationBadgeCount">${state.unreadNotificationCount > 99 ? '99+' : state.unreadNotificationCount}</span>
            </button>

            <div class="notification-dropdown" id="notificationDropdown">
              <div class="notification-dropdown-header">
                <span class="notification-dropdown-title">Thông báo</span>
                <button type="button" class="btn-mark-all-read" id="btnMarkAllNotifsRead">Đã đọc tất cả</button>
              </div>
              <div class="notification-list-items" id="notificationListItems">
                <div style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 0.85rem;">Đang tải thông báo...</div>
              </div>
              <div class="notification-dropdown-footer">
                <a href="${pUrl('/dashboard/#tab-notifications')}">Xem tất cả thông báo &rarr;</a>
              </div>
            </div>
          </div>

          <div class="user-menu-wrapper" id="userMenuWrapper">
            <div class="user-badge" id="userBadgeTrigger" title="Nhấn để mở menu tài khoản">
              <div class="user-avatar">
                ${avatarUrl ? `<img src="${avatarUrl}" alt="${displayName}">` : `<span>${initial}</span>`}
              </div>
              <span class="user-name">${displayName}</span>
              <span class="role-pill ${isCreator ? 'creator' : 'buyer'}">${isCreator ? 'Nghệ sĩ' : 'Người mua'}</span>
            </div>

            <div class="user-dropdown" id="userDropdown">
              <div class="dropdown-header">
                <div class="dropdown-header-name">${displayName}</div>
                <div class="dropdown-header-email">${user.email} &bull; ${isCreator ? 'Nghệ sĩ (Creator)' : 'Người mua (Buyer)'}</div>
              </div>
              
              <a href="${pUrl('/dashboard/')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                <span>Khu vực cá nhân</span>
              </a>

              <a href="${pUrl('/dashboard/#tab-favorites')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                <span>Tác phẩm yêu thích</span>
              </a>

              <a href="${pUrl('/dashboard/#tab-notifications')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
                <span>Thông báo của tôi</span>
              </a>

              ${isCreator ? `
                <div class="dropdown-divider"></div>
                <div style="padding: 6px 12px 2px; font-size: 0.72rem; text-transform: uppercase; font-weight: 700; color: var(--primary-berry); letter-spacing: 0.5px;">Quản lý Nghệ sĩ</div>

                <a href="${pUrl('/artists/' + encodeURIComponent(user.username) + '/')}" class="dropdown-item" style="text-decoration:none; color:inherit; font-weight: 600;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                  <span>Hồ sơ nghệ sĩ của tôi</span>
                </a>

                <a href="${pUrl('/studio/')}" class="dropdown-item" style="text-decoration:none; color:inherit; font-weight: 600; color: var(--primary-berry);">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                  <span>Studio / Quản lý tác phẩm</span>
                </a>

                <a href="${pUrl('/studio/?open=publish')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                  <span>Đăng tác phẩm mới</span>
                </a>

                <a href="${pUrl('/dashboard/#tab-creator-commissions')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                  <span>Yêu cầu đặt vẽ nhận được</span>
                </a>

                <a href="${pUrl('/dashboard/#tab-revenue')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                  <span>Doanh thu & Rút tiền mô phỏng</span>
                </a>

                <div class="dropdown-divider"></div>
                <div style="padding: 6px 12px 2px; font-size: 0.72rem; text-transform: uppercase; font-weight: 700; color: var(--text-muted); letter-spacing: 0.5px;">Mua sắm & Sở hữu</div>
              ` : `
                <div class="dropdown-divider"></div>
              `}

              <a href="${pUrl('/dashboard/#tab-library')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                <span>Tác phẩm đã mua</span>
              </a>

              <a href="${pUrl('/dashboard/#tab-orders')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                <span>${isCreator ? 'Đơn mua tác phẩm' : 'Đơn hàng của tôi'}</span>
              </a>

              <a href="${pUrl('/dashboard/#tab-commissions')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                <span>Yêu cầu đặt vẽ đã gửi</span>
              </a>

              <div class="dropdown-divider"></div>

              <a href="${pUrl('/settings/')}" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                <span>Cài đặt tài khoản</span>
              </a>

              <div class="dropdown-divider"></div>
              <div class="dropdown-item" id="btnLogoutAction" style="color: #C02040; cursor: pointer;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                <span>Đăng xuất</span>
              </div>
            </div>
          </div>
        `;

        // Event handlers for user menu
        const trigger = document.getElementById('userBadgeTrigger');
        const dropdown = document.getElementById('userDropdown');
        if (trigger && dropdown) {
          trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            if (notifDropdown) notifDropdown.classList.remove('show');
            dropdown.classList.toggle('show');
          });
        }

        // Event handlers for notification bell
        const notifBtn = document.getElementById('notificationBellBtn');
        const notifDropdown = document.getElementById('notificationDropdown');
        if (notifBtn && notifDropdown) {
          notifBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (dropdown) dropdown.classList.remove('show');
            notifDropdown.classList.toggle('show');
            renderNotificationDropdownItems();
          });
        }

        document.getElementById('btnMarkAllNotifsRead')?.addEventListener('click', async (e) => {
          e.stopPropagation();
          await markAllNotificationsAsRead();
        });

        // Outside click listener for menus
        document.addEventListener('click', (e) => {
          if (dropdown && !dropdown.contains(e.target) && !trigger?.contains(e.target)) {
            dropdown.classList.remove('show');
          }
          if (notifDropdown && !notifDropdown.contains(e.target) && !notifBtn?.contains(e.target)) {
            notifDropdown.classList.remove('show');
          }
        });

        updateNotificationBadge();

        const btnLogout = document.getElementById('btnLogoutAction');
        if (btnLogout) {
          btnLogout.addEventListener('click', handleLogout);
        }
      }

      if (mobileAuthContainer) {
        mobileAuthContainer.innerHTML = `
          <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 14px;">
            <div class="user-avatar" style="width: 40px; height: 40px; font-size: 1rem;">
              ${avatarUrl ? `<img src="${avatarUrl}" alt="${displayName}">` : `<span>${initial}</span>`}
            </div>
            <div>
              <div style="font-weight: 700; color: var(--text-plum);">${displayName}</div>
              <span class="role-pill ${isCreator ? 'creator' : 'buyer'}">${isCreator ? 'Nghệ sĩ' : 'Người mua'}</span>
            </div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <a href="${pUrl('/dashboard/')}" class="mobile-nav-link">Khu vực cá nhân</a>
            <a href="${pUrl('/dashboard/#tab-favorites')}" class="mobile-nav-link">Tác phẩm yêu thích</a>
            <a href="${pUrl('/dashboard/#tab-notifications')}" class="mobile-nav-link">Thông báo của tôi</a>
            ${isCreator ? `
              <a href="${pUrl('/artists/' + encodeURIComponent(user.username) + '/')}" class="mobile-nav-link" style="color: var(--primary-berry); font-weight: 700;">Hồ sơ nghệ sĩ của tôi</a>
              <a href="${pUrl('/studio/')}" class="mobile-nav-link" style="color: var(--primary-berry); font-weight: 700;">Studio / Quản lý tác phẩm</a>
              <a href="${pUrl('/studio/?open=publish')}" class="mobile-nav-link">Đăng tác phẩm mới</a>
              <a href="${pUrl('/dashboard/#tab-creator-commissions')}" class="mobile-nav-link">Yêu cầu đặt vẽ nhận được</a>
              <a href="${pUrl('/dashboard/#tab-revenue')}" class="mobile-nav-link">Doanh thu & Rút tiền</a>
            ` : ''}
            <a href="${pUrl('/dashboard/#tab-library')}" class="mobile-nav-link">Tác phẩm đã mua</a>
            <a href="${pUrl('/dashboard/#tab-orders')}" class="mobile-nav-link">Đơn hàng</a>
            <a href="${pUrl('/dashboard/#tab-commissions')}" class="mobile-nav-link">Yêu cầu đặt vẽ đã gửi</a>
            <a href="${pUrl('/settings/')}" class="mobile-nav-link">Cài đặt tài khoản</a>
            <button class="btn btn-ghost" id="btnMobileLogout" style="color: #C02040; justify-content: flex-start; padding: 8px 14px; font-size: 0.9rem;">
              Đăng xuất
            </button>
          </div>
        `;
        document.getElementById('btnMobileLogout')?.addEventListener('click', handleLogout);
      }

    } else {
      // Guest state
      if (authContainer) {
        authContainer.innerHTML = `
          <button class="btn btn-ghost" id="navBtnLogin" onclick="window.ArtFair && window.ArtFair.openAuthModal ? window.ArtFair.openAuthModal('login') : null">Đăng nhập</button>
          <button class="btn btn-primary" id="navBtnRegister" onclick="window.ArtFair && window.ArtFair.openAuthModal ? window.ArtFair.openAuthModal('register') : null">Đăng ký</button>
        `;

        document.getElementById('navBtnLogin')?.addEventListener('click', () => openAuthModal('login'));
        document.getElementById('navBtnRegister')?.addEventListener('click', () => openAuthModal('register'));
      }

      if (mobileAuthContainer) {
        mobileAuthContainer.innerHTML = `
          <div style="display: flex; gap: 10px;">
            <button class="btn btn-secondary" id="mobileBtnLogin" style="flex: 1;" onclick="window.ArtFair && window.ArtFair.openAuthModal ? (document.getElementById('mobileDrawerBackdrop')?.classList.remove('show'), document.body.style.overflow='', window.ArtFair.openAuthModal('login')) : null">Đăng nhập</button>
            <button class="btn btn-primary" id="mobileBtnRegister" style="flex: 1;" onclick="window.ArtFair && window.ArtFair.openAuthModal ? (document.getElementById('mobileDrawerBackdrop')?.classList.remove('show'), document.body.style.overflow='', window.ArtFair.openAuthModal('register')) : null">Đăng ký</button>
          </div>
        `;
        document.getElementById('mobileBtnLogin')?.addEventListener('click', () => {
          document.getElementById('mobileDrawerBackdrop')?.classList.remove('show');
          document.body.style.overflow = '';
          openAuthModal('login');
        });
        document.getElementById('mobileBtnRegister')?.addEventListener('click', () => {
          document.getElementById('mobileDrawerBackdrop')?.classList.remove('show');
          document.body.style.overflow = '';
          openAuthModal('register');
        });
      }
    }
  }

  // Close dropdown on outside click
  document.addEventListener('click', () => {
    const dropdown = document.getElementById('userDropdown');
    if (dropdown) dropdown.classList.remove('show');
  });

  // 3. Modal Management
  let lastFocusedOpener = null;

  function openAuthModal(tab = 'login') {
    lastFocusedOpener = document.activeElement;
    const backdrop = document.getElementById('authModalBackdrop');
    if (!backdrop) return;

    // If user is currently unauthenticated, wipe any orphan or stale token so fresh auth is clean
    if (!state.currentUser) {
      setAuthToken('');
    }

    // Lock background scroll
    document.body.classList.add('modal-open');
    document.body.style.overflow = 'hidden';

    backdrop.classList.add('show');
    switchAuthTab(tab);
    clearAuthAlerts();

    // Reset scroll position to top
    const modalBody = backdrop.querySelector('.modal-body');
    if (modalBody) modalBody.scrollTop = 0;

    // Focus initial input
    setTimeout(() => {
      if (tab === 'login') {
        document.getElementById('loginUsername')?.focus();
      } else {
        document.getElementById('regUsername')?.focus();
      }
    }, 80);
  }

  function closeAuthModal() {
    const backdrop = document.getElementById('authModalBackdrop');
    if (!backdrop) return;
    backdrop.classList.remove('show');

    // Restore background scroll
    document.body.classList.remove('modal-open');
    document.body.style.overflow = '';

    clearAuthAlerts();

    // Return focus to trigger button
    if (lastFocusedOpener && typeof lastFocusedOpener.focus === 'function') {
      try { lastFocusedOpener.focus(); } catch (_) {}
    }
  }

  function switchAuthTab(tab) {
    const tabLoginBtn = document.getElementById('tabLoginBtn');
    const tabRegisterBtn = document.getElementById('tabRegisterBtn');
    const paneLogin = document.getElementById('paneLogin');
    const paneRegister = document.getElementById('paneRegister');

    if (tab === 'login') {
      tabLoginBtn?.classList.add('active');
      tabRegisterBtn?.classList.remove('active');
      paneLogin?.classList.add('active');
      paneRegister?.classList.remove('active');
    } else {
      tabRegisterBtn?.classList.add('active');
      tabLoginBtn?.classList.remove('active');
      paneRegister?.classList.add('active');
      paneLogin?.classList.remove('active');
    }

    // Always scroll modal body back to top on tab switch
    const modalBody = document.querySelector('#authModalBackdrop .modal-body');
    if (modalBody) modalBody.scrollTop = 0;

    clearAuthAlerts();

    setTimeout(() => {
      if (tab === 'login') {
        document.getElementById('loginUsername')?.focus();
      } else {
        document.getElementById('regUsername')?.focus();
      }
    }, 60);
  }

  function clearAuthAlerts() {
    const alerts = document.querySelectorAll('#authModalBackdrop .form-alert');
    alerts.forEach(el => {
      el.className = el.classList.contains('form-alert-bottom') ? 'form-alert form-alert-bottom' : 'form-alert';
      el.textContent = '';
      el.style.display = 'none';
    });
    document.querySelectorAll('#authModalBackdrop .form-input').forEach(input => {
      input.classList.remove('input-error');
    });
  }

  // 4. Handle Login Form Submit
  async function handleLogin(e) {
    e.preventDefault();
    clearAuthAlerts();

    const btn = document.getElementById('btnLoginSubmit');
    const alertBox = document.getElementById('loginAlert');
    const usernameInput = document.getElementById('loginUsername');
    const passwordInput = document.getElementById('loginPassword');

    const username = (usernameInput?.value || '').trim();
    const password = passwordInput?.value || '';

    if (!username) {
      usernameInput?.classList.add('input-error');
      showAlert(alertBox, 'Vui lòng nhập tên đăng nhập.', 'error');
      usernameInput?.focus();
      return;
    }

    if (!password) {
      passwordInput?.classList.add('input-error');
      showAlert(alertBox, 'Vui lòng nhập mật khẩu.', 'error');
      passwordInput?.focus();
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Đang đăng nhập...';
    }

    try {
      const res = await apiFetch('/api/accounts/auth/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
      });

      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        if (data.token) {
          setAuthToken(data.token);
        }
        if (data.csrf_token) {
          syncCsrfToken(data.csrf_token);
        } else {
          getCsrfToken();
        }

        if (data.user) {
          state.currentUser = data.user;
        }
        renderNavbarAuth();
        showToast('Đăng nhập thành công!', 'success');
        closeAuthModal();

        await checkCurrentUser();
        window.dispatchEvent(new CustomEvent('artfair:login_success', { detail: data }));

        const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;

        // Handle returnUrl / next parameter safely (prevent external open-redirects)
        const urlParams = new URLSearchParams(window.location.search);
        const nextUrl = urlParams.get('next');
        if (nextUrl && nextUrl.startsWith('/') && !nextUrl.startsWith('//')) {
          setTimeout(() => { window.location.href = pUrl(nextUrl); }, 350);
          return;
        }

        // Auto-redirect to studio if user is a creator and currently on guest landing
        if (data.user && data.user.role === 'CREATOR' && (window.location.pathname === '/' || window.location.pathname.endsWith('/ARTFAIR/'))) {
          setTimeout(() => { window.location.href = pUrl('/studio/'); }, 400);
          return;
        }

        // Reload if on protected server-rendered views
        if (window.location.pathname.includes('/studio') ||
            window.location.pathname.includes('/dashboard') ||
            window.location.pathname.includes('/settings') ||
            window.location.pathname.includes('/commissions')) {
          setTimeout(() => { window.location.reload(); }, 350);
        }
      } else {
        const errorMsg = data.detail || (data.non_field_errors && data.non_field_errors[0]) || 'Đăng nhập không thành công. Vui lòng kiểm tra lại tài khoản và mật khẩu.';
        showAlert(alertBox, errorMsg, 'error');
      }
    } catch (err) {
      showAlert(alertBox, 'Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối mạng và thử lại.', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Đăng nhập';
      }
    }
  }

  // 5. Handle Register Form Submit
  async function handleRegister(e) {
    e.preventDefault();
    clearAuthAlerts();

    const btn = document.getElementById('btnRegisterSubmit');
    const alertBox = document.getElementById('registerAlert');
    const usernameInput = document.getElementById('regUsername');
    const emailInput = document.getElementById('regEmail');
    const passwordInput = document.getElementById('regPassword');
    const confirmPasswordInput = document.getElementById('regConfirmPassword');
    const agreeTermsInput = document.getElementById('regAgreeTerms');
    const roleInput = document.querySelector('input[name="regRole"]:checked');

    const username = (usernameInput?.value || '').trim();
    const email = (emailInput?.value || '').trim();
    const password = passwordInput?.value || '';
    const confirmPassword = confirmPasswordInput?.value || '';
    const agreeTerms = agreeTermsInput ? agreeTermsInput.checked : true;
    const role = roleInput ? roleInput.value : 'BUYER';

    // Client-side validations with direct visual feedback
    if (!username) {
      usernameInput?.classList.add('input-error');
      showAlert(alertBox, 'Vui lòng nhập tên đăng nhập.', 'error');
      usernameInput?.focus();
      return;
    }

    if (username.length < 3) {
      usernameInput?.classList.add('input-error');
      showAlert(alertBox, 'Tên đăng nhập phải có ít nhất 3 ký tự.', 'error');
      usernameInput?.focus();
      return;
    }

    if (!/^[a-zA-Z0-9_.-]+$/.test(username)) {
      usernameInput?.classList.add('input-error');
      showAlert(alertBox, 'Tên đăng nhập chỉ được chứa chữ cái, chữ số, dấu gạch dưới (_), gạch ngang (-) hoặc chấm (.).', 'error');
      usernameInput?.focus();
      return;
    }

    if (!email) {
      emailInput?.classList.add('input-error');
      showAlert(alertBox, 'Vui lòng nhập địa chỉ email hợp lệ.', 'error');
      emailInput?.focus();
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      emailInput?.classList.add('input-error');
      showAlert(alertBox, 'Địa chỉ email không đúng định dạng. Ví dụ: name@example.com', 'error');
      emailInput?.focus();
      return;
    }

    if (!password) {
      passwordInput?.classList.add('input-error');
      showAlert(alertBox, 'Vui lòng nhập mật khẩu.', 'error');
      passwordInput?.focus();
      return;
    }

    if (password.length < 8) {
      passwordInput?.classList.add('input-error');
      showAlert(alertBox, 'Mật khẩu phải có tối thiểu 8 ký tự để đảm bảo an toàn.', 'error');
      passwordInput?.focus();
      return;
    }

    if (confirmPasswordInput && password !== confirmPassword) {
      confirmPasswordInput?.classList.add('input-error');
      showAlert(alertBox, 'Mật khẩu xác nhận không khớp. Vui lòng kiểm tra lại.', 'error');
      confirmPasswordInput?.focus();
      return;
    }

    if (agreeTermsInput && !agreeTerms) {
      showAlert(alertBox, 'Vui lòng đánh dấu đồng ý với Điều khoản dịch vụ và Chính sách bảo mật của ARTFAIR.', 'error');
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Đang xử lý tạo tài khoản...';
    }

    try {
      const res = await apiFetch('/api/accounts/auth/register/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, email, password, role })
      });

      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        if (data.token) {
          setAuthToken(data.token);
        }
        if (data.csrf_token) {
          syncCsrfToken(data.csrf_token);
        } else {
          getCsrfToken();
        }

        // Establish user in state immediately
        state.currentUser = data;
        renderNavbarAuth();
        window.dispatchEvent(new CustomEvent('artfair:login_success', { detail: { username, role, user: data } }));

        // Attempt silent session login in background (non-blocking)
        apiFetch('/api/accounts/auth/login/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        }).then(async (lRes) => {
          if (lRes.ok) {
            const lData = await lRes.json().catch(() => ({}));
            if (lData.token) setAuthToken(lData.token);
            if (lData.csrf_token) syncCsrfToken(lData.csrf_token);
          }
        }).catch(() => {});

        closeAuthModal();

        const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;
        const urlParams = new URLSearchParams(window.location.search);
        const nextUrl = urlParams.get('next');

        if (nextUrl && nextUrl.startsWith('/') && !nextUrl.startsWith('//')) {
          showToast('Đăng ký thành công! Đang chuyển hướng...', 'success');
          setTimeout(() => { window.location.href = pUrl(nextUrl); }, 500);
          return;
        }

        if (role === 'CREATOR') {
          showToast('Chào mừng Nghệ sĩ mới! Đang chuyển đến Creator Studio...', 'success');
          setTimeout(() => { window.location.href = pUrl('/studio/'); }, 500);
          return;
        }

        // BUYER registered: redirect directly to Personal Dashboard so they immediately see their live portal!
        showToast('Chào mừng bạn đến với ARTFAIR! Đang chuyển đến Bảng điều khiển cá nhân...', 'success');
        setTimeout(() => { window.location.href = pUrl('/dashboard/'); }, 500);
        return;

      } else {
        // Detailed error parsing
        let msgLines = [];
        if (data.username) {
          usernameInput?.classList.add('input-error');
          const txt = Array.isArray(data.username) ? data.username.join(' ') : data.username;
          msgLines.push(`• Tên đăng nhập: ${txt}`);
        }
        if (data.email) {
          emailInput?.classList.add('input-error');
          const txt = Array.isArray(data.email) ? data.email.join(' ') : data.email;
          msgLines.push(`• Email: ${txt}`);
        }
        if (data.password) {
          passwordInput?.classList.add('input-error');
          const txt = Array.isArray(data.password) ? data.password.join(' ') : data.password;
          msgLines.push(`• Mật khẩu: ${txt}`);
        }
        if (data.detail) {
          msgLines.push(`• ${data.detail}`);
        }
        if (data.non_field_errors) {
          const txt = Array.isArray(data.non_field_errors) ? data.non_field_errors.join(' ') : data.non_field_errors;
          msgLines.push(`• ${txt}`);
        }
        if (msgLines.length === 0) {
          for (const key of Object.keys(data)) {
            const val = data[key];
            const txt = Array.isArray(val) ? val.join(' ') : String(val);
            msgLines.push(`• ${key}: ${txt}`);
          }
        }
        const fullMsg = msgLines.length > 0 ? ('Đăng ký chưa thành công:\n' + msgLines.join('\n')) : 'Đăng ký không thành công. Vui lòng kiểm tra lại thông tin.';
        showAlert(alertBox, fullMsg, 'error');
      }
    } catch (err) {
      showAlert(alertBox, 'Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối mạng và thử lại.', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Tạo tài khoản';
      }
    }
  }

  // 6. Handle Logout
  async function handleLogout() {
    try {
      const res = await apiFetch('/api/accounts/auth/logout/', {
        method: 'POST'
      });
      const data = await res.json().catch(() => ({}));
      if (data.csrf_token) {
        syncCsrfToken(data.csrf_token);
      } else {
        getCsrfToken();
      }
    } catch (err) {}
    setAuthToken(null);
    state.currentUser = null;
    state.favoriteIds = new Set();
    state.notifications = [];
    state.unreadNotificationCount = 0;
    renderNavbarAuth();
    window.dispatchEvent(new CustomEvent('artfair:user_loaded', { detail: null }));
    showToast('Đã đăng xuất khỏi tài khoản.', 'info');

    // If user was on protected pages, redirect to home page
    const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;
    if (window.location.pathname.includes('/dashboard') || 
        window.location.pathname.includes('/studio') || 
        window.location.pathname.includes('/settings') ||
        window.location.pathname.includes('/commissions')) {
      setTimeout(() => { window.location.href = pUrl('/'); }, 300);
    }
  }

  // 6b. Secure Token Authenticated Download Helpers
  async function downloadOriginalArtworkFile(artworkId, defaultFilename = 'artwork_original') {
    try {
      showToast('Đang chuẩn bị tệp tải xuống...', 'info');
      const url = `/api/artworks/${artworkId}/download-file/`;
      const res = await apiFetch(url);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Không thể tải tệp gốc. Vui lòng kiểm tra quyền sở hữu hoặc đăng nhập lại.', 'error');
        return;
      }
      const blob = await res.blob();
      const disposition = res.headers.get('Content-Disposition');
      let filename = defaultFilename;
      if (disposition && disposition.indexOf('filename=') !== -1) {
        const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i);
        if (match && match[1]) filename = decodeURIComponent(match[1]);
      }
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);
      showToast('Bắt đầu tải xuống tệp gốc thành công.', 'success');
    } catch (err) {
      console.error('Download error:', err);
      showToast('Lỗi khi tải tệp gốc: ' + (err.message || 'Lỗi kết nối'), 'error');
    }
  }

  async function downloadOrderCertificate(orderCode) {
    try {
      showToast('Đang xuất chứng chỉ bản quyền PDF...', 'info');
      const url = `/api/artworks/orders/${orderCode}/certificate/`;
      const res = await apiFetch(url);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Không thể tải chứng nhận bản quyền.', 'error');
        return;
      }
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      window.open(blobUrl, '_blank');
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60000);
    } catch (err) {
      console.error('Certificate download error:', err);
      showToast('Lỗi khi tải chứng nhận.', 'error');
    }
  }

  // Intercept click on download / certificate links to ensure token-authenticated blob downloads
  document.addEventListener('click', function(e) {
    const downloadLink = e.target.closest('a[href*="/download-file/"]');
    if (downloadLink) {
      e.preventDefault();
      const match = downloadLink.href.match(/\/artworks\/(\d+)\/download-file\//);
      if (match) {
        downloadOriginalArtworkFile(match[1]);
      }
      return;
    }
    const certLink = e.target.closest('a[href*="/certificate/"]');
    if (certLink) {
      e.preventDefault();
      const match = certLink.href.match(/\/orders\/([^/]+)\/certificate\//);
      if (match) {
        downloadOrderCertificate(match[1]);
      }
      return;
    }
  });

  function showAlert(elem, msg, type = 'error') {
    if (!elem) return;
    elem.className = elem.classList.contains('form-alert-bottom') ? `form-alert form-alert-bottom show ${type}` : `form-alert show ${type}`;
    elem.innerText = msg;
    elem.style.display = 'block';

    // Also mirror to sibling bottom alert if available
    const pane = elem.closest('.tab-pane') || elem.closest('form');
    if (pane) {
      const bottomAlert = pane.querySelector('.form-alert-bottom');
      if (bottomAlert && bottomAlert !== elem) {
        bottomAlert.className = `form-alert form-alert-bottom show ${type}`;
        bottomAlert.innerText = msg;
        bottomAlert.style.display = 'block';
      }
    }

    // Scroll modal-body so the user definitely sees the alert
    const modalBody = document.querySelector('#authModalBackdrop .modal-body');
    if (modalBody) {
      modalBody.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  // 7. Load Categories & Tags
  async function loadTaxonomies() {
    try {
      const [catRes, tagRes] = await Promise.all([
        apiFetch('/api/artworks/categories/'),
        apiFetch('/api/artworks/tags/')
      ]);

      if (catRes.ok) {
        state.categories = await catRes.json();
        renderCategoryPills();
      }

      if (tagRes.ok) {
        state.tags = await tagRes.json();
        renderTagFilterOptions();
      }
    } catch (err) {
      console.error('Failed to load categories or tags', err);
    }
  }

  function renderCategoryPills() {
    const container = document.getElementById('categoryPills');
    if (!container) return;

    let html = `
      <button class="pill-btn ${state.filters.category === '' ? 'active' : ''}" data-cat-slug="">
        Tất cả
      </button>
    `;

    state.categories.forEach(cat => {
      const isActive = state.filters.category === cat.slug;
      html += `
        <button class="pill-btn ${isActive ? 'active' : ''}" data-cat-slug="${cat.slug}">
          ${cat.name}
        </button>
      `;
    });

    container.innerHTML = html;

    container.querySelectorAll('.pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const slug = btn.getAttribute('data-cat-slug');
        state.filters.category = slug;
        state.filters.page = 1;
        renderCategoryPills();
        loadArtworks();
      });
    });
  }

  function renderTagFilterOptions() {
    const select = document.getElementById('filterTagSelect');
    if (!select) return;

    let html = `<option value="">Tất cả các thẻ</option>`;
    state.tags.forEach(tag => {
      html += `<option value="${tag.slug}">#${tag.name}</option>`;
    });
    select.innerHTML = html;
  }

  // 8. Load Artworks Gallery (Real API)
  async function loadArtworks() {
    const grid = document.getElementById('artworksGrid');
    const pagination = document.getElementById('paginationWrapper');
    if (!grid) return;

    // Show skeletons while loading
    renderSkeletons(grid);

    // Build Query String
    const params = new URLSearchParams();
    params.set('page', state.filters.page);

    if (state.filters.category) params.set('category', state.filters.category);
    if (state.filters.tag) params.set('tag', state.filters.tag);
    if (state.filters.style) params.set('style', state.filters.style);
    if (state.filters.license_type) params.set('license_type', state.filters.license_type);
    if (state.filters.min_price) params.set('min_price', state.filters.min_price);
    if (state.filters.max_price) params.set('max_price', state.filters.max_price);
    if (state.filters.search) params.set('search', state.filters.search);
    if (state.filters.ordering) params.set('ordering', state.filters.ordering);

    try {
      const res = await apiFetch(`/api/artworks/?${params.toString()}`);
      if (!res.ok) {
        throw new Error('API response was not ok');
      }

      const data = await res.json();
      const results = data.results || [];
      const totalCount = data.count || 0;

      if (results.length === 0) {
        renderEmptyState(grid);
        if (pagination) pagination.innerHTML = '';
        return;
      }

      renderArtworks(grid, results);
      renderPagination(totalCount);

    } catch (err) {
      renderErrorState(grid);
      if (pagination) pagination.innerHTML = '';
    }
  }

  function renderSkeletons(container) {
    let html = '';
    for (let i = 0; i < 8; i++) {
      html += `
        <div class="skeleton-card">
          <div class="skeleton-img"></div>
          <div class="skeleton-text" style="width: 70%;"></div>
          <div class="skeleton-text short"></div>
          <div class="skeleton-text price"></div>
        </div>
      `;
    }
    container.innerHTML = html;
  }

  function renderEmptyState(container) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1;">
        <div class="state-notice-box">
          <svg class="state-notice-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            <line x1="8" y1="11" x2="14" y2="11"></line>
          </svg>
          <h3 class="state-notice-title">Không tìm thấy tác phẩm</h3>
          <p class="state-notice-desc">Không có tác phẩm nào phù hợp với bộ lọc hiện tại. Hãy thử chọn danh mục khác hoặc đặt lại bộ lọc.</p>
          <button class="btn btn-primary" id="btnResetFiltersEmpty">Đặt lại bộ lọc</button>
        </div>
      </div>
    `;

    document.getElementById('btnResetFiltersEmpty')?.addEventListener('click', resetFilters);
  }

  function renderErrorState(container) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1;">
        <div class="state-notice-box">
          <svg class="state-notice-icon" viewBox="0 0 24 24" fill="none" stroke="#DC3545" stroke-width="1.8">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <h3 class="state-notice-title">Lỗi kết nối máy chủ</h3>
          <p class="state-notice-desc">Không thể tải danh sách tác phẩm nghệ thuật vào lúc này. Vui lòng kiểm tra lại kết nối.</p>
          <button class="btn btn-primary" onclick="window.ArtFair.reloadArtworks()">Thử lại</button>
        </div>
      </div>
    `;
  }

  window.ArtFair.reloadArtworks = loadArtworks;

  function renderArtworks(container, artworks) {
    let html = '';

    artworks.forEach(art => {
      // Find starting price
      const licenses = art.license_options || [];
      let startingPrice = null;
      let priceLabel = 'Từ ';

      if (state.filters.license_type) {
        // Specific license selected
        const targetLic = licenses.find(l => l.license_type === state.filters.license_type);
        if (targetLic) {
          startingPrice = Number(targetLic.price);
          priceLabel = '';
        }
      }

      if (startingPrice === null && licenses.length > 0) {
        const prices = licenses.map(l => Number(l.price)).filter(p => !isNaN(p) && p > 0);
        if (prices.length > 0) {
          startingPrice = Math.min(...prices);
        }
      }

      const isFav = state.favoriteIds.has(Number(art.id));
      const formattedPrice = startingPrice ? `${priceLabel}${formatVND(startingPrice)}` : 'Chưa định giá';
      const artistName = (art.creator && art.creator.display_name) ? art.creator.display_name : (art.creator?.username || 'Nghệ sĩ ArtFair');
      const artistUsername = art.creator?.username;
      const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;
      const mUrl = (path) => (window.ArtFairConfig && window.ArtFairConfig.mediaUrl) ? window.ArtFairConfig.mediaUrl(path) : path;
      const artistProfileUrl = artistUsername ? pUrl(`/artists/${encodeURIComponent(artistUsername)}/`) : null;
      const artistHtml = artistProfileUrl
        ? `<a href="${artistProfileUrl}" class="art-card-artist-link" onclick="event.stopPropagation();">${artistName}</a>`
        : artistName;
      const categoryName = art.category ? art.category.name : '';
      const previewSrc = mUrl(art.preview_image || '');

      html += `
        <article class="art-card" data-artwork-id="${art.id}">
          <div class="art-card-img-wrap">
            <img class="art-card-img protected-artwork-img" src="${previewSrc}" alt="${art.title}" loading="lazy" draggable="false" style="object-fit: cover; object-position: center;">
            <div style="position: absolute; top: 10px; left: 10px; display: flex; flex-direction: column; gap: 4px; z-index: 2;">
              <span class="art-card-status-badge">Đang bán</span>
              ${categoryName ? `<span class="art-card-badge">${categoryName}</span>` : ''}
              ${art.style ? `<span class="art-card-style-badge">${art.style}</span>` : ''}
              ${state.filters.license_type ? `<span class="art-card-license-badge">Quyền: <strong>${state.filters.license_type}</strong></span>` : ''}
            </div>
            <button class="art-card-favorite-btn ${isFav ? 'active' : ''}" data-artwork-id="${art.id}" title="${isFav ? 'Bỏ lưu yêu thích' : 'Yêu thích'}">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="${isFav ? '#E11D48' : 'none'}" stroke="${isFav ? '#E11D48' : 'currentColor'}" stroke-width="2">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
              </svg>
            </button>
          </div>
          <div class="art-card-body">
            <h3 class="art-card-title" title="${art.title}"><strong>${art.title}</strong></h3>
            <div class="art-card-artist"><span class="art-card-by-label">Nghệ sĩ:</span> <strong>${artistHtml}</strong></div>
            <div class="art-card-price-row">
              <span class="art-card-price"><strong>${formattedPrice}</strong></span>
              <span class="art-card-license-hint"><strong class="hint-count">${licenses.length}</strong> gói quyền</span>
            </div>
          </div>
        </article>
      `;
    });

    container.innerHTML = html;

    // Attach card click handlers for Quick View & Favorites
    container.querySelectorAll('.art-card').forEach(card => {
      const artId = card.getAttribute('data-artwork-id');
      const artObj = artworks.find(a => a.id == artId);

      // Favorite button
      const favBtn = card.querySelector('.art-card-favorite-btn');
      favBtn?.addEventListener('click', async (e) => {
        e.stopPropagation();
        e.preventDefault();
        if (!state.currentUser) {
          showToast('Vui lòng đăng nhập để lưu tác phẩm yêu thích.', 'info');
          openAuthModal('login');
          return;
        }
        await toggleArtworkFavorite(artId, favBtn);
      });

      // Card click opens artwork detail page
      card.addEventListener('click', () => {
        const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;
        if (artObj && artObj.slug) {
          window.location.href = pUrl(`/artworks/${artObj.slug}/`);
        } else if (artObj) {
          openQuickViewModal(artObj);
        }
      });
    });

    protectArtworkImages();
  }

  // 9. Quick View Artwork Modal
  function openQuickViewModal(art) {
    const backdrop = document.getElementById('quickViewBackdrop');
    if (!backdrop) return;

    const mUrl = (path) => (window.ArtFairConfig && window.ArtFairConfig.mediaUrl) ? window.ArtFairConfig.mediaUrl(path) : path;
    const imgElem = document.getElementById('qvImage');
    const titleElem = document.getElementById('qvTitle');
    const artistElem = document.getElementById('qvArtist');
    const categoryElem = document.getElementById('qvCategory');
    const tagsElem = document.getElementById('qvTags');
    const descElem = document.getElementById('qvDesc');
    const tiersElem = document.getElementById('qvLicenseTiers');

    if (imgElem) imgElem.src = mUrl(art.preview_image || '');
    if (titleElem) titleElem.textContent = art.title;
    if (artistElem) artistElem.textContent = (art.creator && art.creator.display_name) ? art.creator.display_name : (art.creator?.username || 'Nghệ sĩ ArtFair');
    if (categoryElem) categoryElem.textContent = art.category ? art.category.name : '';
    if (descElem) descElem.textContent = art.description || 'Tác phẩm nghệ thuật số độc quyền trên nền tảng ARTFAIR.';

    // Tags
    if (tagsElem) {
      if (art.tags && art.tags.length > 0) {
        tagsElem.innerHTML = art.tags.map(t => `<span class="role-pill" style="background:#F1E8FF; color:#6B3BA7;">#${t.name}</span>`).join(' ');
      } else {
        tagsElem.innerHTML = '';
      }
    }

    // License tiers
    if (tiersElem) {
      const licenses = art.license_options || [];
      if (licenses.length > 0) {
        tiersElem.innerHTML = licenses.map(lic => {
          const typeName = lic.license_type === 'COMMERCIAL' ? 'Thương mại (Commercial)' : 'Cá nhân (Personal)';
          return `
            <div class="license-tier-item">
              <div>
                <div class="tier-name">${typeName}</div>
                <div class="tier-terms">${lic.terms || 'Quyền sử dụng không độc quyền.'}</div>
              </div>
              <div class="tier-price">${formatVND(lic.price)}</div>
            </div>
          `;
        }).join('');
      } else {
        tiersElem.innerHTML = `<div style="font-size: 0.85rem; color: var(--text-muted);">Chưa có thông tin gói quyền.</div>`;
      }
    }

    const qvBuyBtn = document.getElementById('qvBuyBtn');
    if (qvBuyBtn) {
      qvBuyBtn.onclick = () => {
        closeQuickViewModal();
        if (art.slug) {
          const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;
          window.location.href = pUrl(`/artworks/${art.slug}/`);
        }
      };
    }

    backdrop.classList.add('show');
  }

  function closeQuickViewModal() {
    const backdrop = document.getElementById('quickViewBackdrop');
    if (backdrop) backdrop.classList.remove('show');
  }

  // 10. Pagination rendering
  function renderPagination(totalCount) {
    const container = document.getElementById('paginationWrapper');
    if (!container) return;

    const pageSize = 12;
    const totalPages = Math.ceil(totalCount / pageSize);

    if (totalPages <= 1) {
      container.innerHTML = '';
      return;
    }

    let html = `
      <button class="page-btn" id="pageBtnPrev" ${state.filters.page <= 1 ? 'disabled' : ''}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"></polyline></svg>
      </button>
    `;

    for (let p = 1; p <= totalPages; p++) {
      html += `
        <button class="page-btn ${p === state.filters.page ? 'active' : ''}" data-page="${p}">
          ${p}
        </button>
      `;
    }

    html += `
      <button class="page-btn" id="pageBtnNext" ${state.filters.page >= totalPages ? 'disabled' : ''}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
      </button>
    `;

    container.innerHTML = html;

    // Attach listeners
    container.querySelectorAll('[data-page]').forEach(btn => {
      btn.addEventListener('click', () => {
        const pageNum = parseInt(btn.getAttribute('data-page'));
        if (pageNum !== state.filters.page) {
          state.filters.page = pageNum;
          loadArtworks();
          scrollToGallery();
        }
      });
    });

    document.getElementById('pageBtnPrev')?.addEventListener('click', () => {
      if (state.filters.page > 1) {
        state.filters.page--;
        loadArtworks();
        scrollToGallery();
      }
    });

    document.getElementById('pageBtnNext')?.addEventListener('click', () => {
      if (state.filters.page < totalPages) {
        state.filters.page++;
        loadArtworks();
        scrollToGallery();
      }
    });
  }

  function scrollToGallery() {
    const sec = document.getElementById('gallerySection');
    if (sec) {
      sec.scrollIntoView({ behavior: 'smooth' });
    }
  }

  function resetFilters() {
    state.filters = {
      page: 1,
      category: '',
      tag: '',
      style: '',
      license_type: '',
      min_price: '',
      max_price: '',
      search: '',
      ordering: '-created_at'
    };

    // Reset input elements
    const searchNav = document.getElementById('navSearchInput');
    const sortSelect = document.getElementById('sortSelect');
    const filterLic = document.getElementById('filterLicenseSelect');
    const filterTag = document.getElementById('filterTagSelect');
    const filterStyle = document.getElementById('filterStyleSelect');
    const minPriceInput = document.getElementById('filterMinPrice');
    const maxPriceInput = document.getElementById('filterMaxPrice');

    if (searchNav) searchNav.value = '';
    if (sortSelect) sortSelect.value = '-created_at';
    if (filterLic) filterLic.value = '';
    if (filterTag) filterTag.value = '';
    if (filterStyle) filterStyle.value = '';
    if (minPriceInput) minPriceInput.value = '';
    renderCategoryPills();
    loadArtworks();
  }

  function parseUrlQueryParams() {
    const params = new URLSearchParams(window.location.search);
    let hasFilter = false;

    if (params.get('search')) {
      state.filters.search = params.get('search');
      const searchNav = document.getElementById('navSearchInput');
      if (searchNav) searchNav.value = state.filters.search;
      hasFilter = true;
    }
    if (params.get('category')) {
      state.filters.category = params.get('category');
      hasFilter = true;
    }
    if (params.get('tag')) {
      state.filters.tag = params.get('tag');
      const filterTag = document.getElementById('filterTagSelect');
      if (filterTag) filterTag.value = state.filters.tag;
      hasFilter = true;
    }
    if (params.get('style')) {
      state.filters.style = params.get('style');
      const filterStyle = document.getElementById('filterStyleSelect');
      if (filterStyle) filterStyle.value = state.filters.style;
      hasFilter = true;
    }
    if (params.get('license_type')) {
      state.filters.license_type = params.get('license_type');
      const filterLic = document.getElementById('filterLicenseSelect');
      if (filterLic) filterLic.value = state.filters.license_type;
      hasFilter = true;
    }
    if (params.get('min_price')) {
      state.filters.min_price = params.get('min_price');
      const minPrice = document.getElementById('filterMinPrice');
      if (minPrice) minPrice.value = state.filters.min_price;
      hasFilter = true;
    }
    if (params.get('max_price')) {
      state.filters.max_price = params.get('max_price');
      const maxPrice = document.getElementById('filterMaxPrice');
      if (maxPrice) maxPrice.value = state.filters.max_price;
      hasFilter = true;
    }

    if (hasFilter || window.location.hash === '#gallerySection') {
      setTimeout(() => {
        scrollToGallery();
      }, 350);
    }
  }

  function setupCategoryPills() {
    const container = document.getElementById('categoryPills');
    if (!container) return;
    if (state.filters.category) {
      container.querySelectorAll('.pill-btn').forEach(btn => {
        const catSlug = btn.getAttribute('data-cat-slug') || '';
        btn.classList.toggle('active', catSlug === state.filters.category);
      });
    }
    container.querySelectorAll('.pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        container.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.filters.category = btn.getAttribute('data-cat-slug') || '';
        state.filters.page = 1;
        loadArtworks();
      });
    });
  }

  // 11. Initial DOM Ready Bindings
  document.addEventListener('DOMContentLoaded', () => {
    initCsrfToken();
    parseUrlQueryParams();
    setupCategoryPills();
    loadArtworks();
    checkCurrentUser();
    protectArtworkImages();

    // Initial guest auth button listeners
    document.getElementById('navBtnLogin')?.addEventListener('click', () => openAuthModal('login'));
    document.getElementById('navBtnRegister')?.addEventListener('click', () => openAuthModal('register'));

    // Modal Tabs
    document.getElementById('tabLoginBtn')?.addEventListener('click', () => switchAuthTab('login'));
    document.getElementById('tabRegisterBtn')?.addEventListener('click', () => switchAuthTab('register'));

    // Modal Close
    document.getElementById('modalCloseBtn')?.addEventListener('click', closeAuthModal);
    document.getElementById('authModalBackdrop')?.addEventListener('click', (e) => {
      if (e.target.id === 'authModalBackdrop') closeAuthModal();
    });

    // Quick View Modal Close
    document.getElementById('qvCloseBtn')?.addEventListener('click', closeQuickViewModal);
    document.getElementById('quickViewBackdrop')?.addEventListener('click', (e) => {
      if (e.target.id === 'quickViewBackdrop') closeQuickViewModal();
    });

    // Modal Accessibility: Escape Key & Focus Trap
    document.addEventListener('keydown', (e) => {
      const authModal = document.getElementById('authModalBackdrop');
      if (authModal && authModal.classList.contains('show')) {
        if (e.key === 'Escape') {
          e.preventDefault();
          closeAuthModal();
          return;
        }
        if (e.key === 'Tab') {
          const focusables = authModal.querySelectorAll(
            'button, [href], input:not([type="hidden"]), select, textarea, [tabindex]:not([tabindex="-1"])'
          );
          const visible = Array.prototype.filter.call(focusables, el => el.offsetParent !== null && !el.disabled);
          if (visible.length > 0) {
            const first = visible[0];
            const last = visible[visible.length - 1];
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        }
        return;
      }

      if (e.key === 'Escape') {
        closeQuickViewModal();
      }
    });

    // Form Submissions
    document.getElementById('formLogin')?.addEventListener('submit', handleLogin);
    document.getElementById('formRegister')?.addEventListener('submit', handleRegister);

    // Password Toggle Buttons
    setupPasswordToggle('toggleLoginPassword', 'loginPassword');
    setupPasswordToggle('toggleRegPassword', 'regPassword');

    // Role Radio Card Selector in Register Modal
    document.querySelectorAll('.role-radio-card').forEach(card => {
      card.setAttribute('tabindex', '0');
      card.setAttribute('role', 'radio');
      const radio = card.querySelector('input[type="radio"]');
      card.setAttribute('aria-checked', radio && radio.checked ? 'true' : 'false');

      const selectCard = () => {
        document.querySelectorAll('.role-radio-card').forEach(c => {
          c.classList.remove('active');
          c.setAttribute('aria-checked', 'false');
          const r = c.querySelector('input[type="radio"]');
          if (r) r.checked = false;
        });
        card.classList.add('active');
        card.setAttribute('aria-checked', 'true');
        if (radio) radio.checked = true;
      };

      card.addEventListener('click', selectCard);
      card.addEventListener('keydown', (e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          selectCard();
        }
      });
    });

    // Search Input (Navbar)
    const navSearch = document.getElementById('navSearchInput');
    let searchDebounceTimer;
    navSearch?.addEventListener('input', (e) => {
      const grid = document.getElementById('artworksGrid');
      if (!grid) return;
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        state.filters.search = e.target.value.trim();
        state.filters.page = 1;
        loadArtworks();
      }, 400);
    });

    navSearch?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const query = e.target.value.trim();
        if (window.location.pathname !== '/') {
          window.location.href = `/?search=${encodeURIComponent(query)}#gallerySection`;
        } else {
          state.filters.search = query;
          state.filters.page = 1;
          loadArtworks();
          scrollToGallery();
        }
      }
    });

    // Sorter select
    const sortSelect = document.getElementById('sortSelect');
    sortSelect?.addEventListener('change', (e) => {
      state.filters.ordering = e.target.value;
      state.filters.page = 1;
      loadArtworks();
    });

    // Advanced Filter Toggle
    const filterToggleBtn = document.getElementById('filterToggleBtn');
    const advancedPanel = document.getElementById('advancedFilterPanel');
    filterToggleBtn?.addEventListener('click', () => {
      filterToggleBtn.classList.toggle('active');
      advancedPanel?.classList.toggle('show');
    });

    // Advanced Filter Form Apply
    document.getElementById('btnApplyAdvancedFilters')?.addEventListener('click', () => {
      const licSelect = document.getElementById('filterLicenseSelect');
      const tagSelect = document.getElementById('filterTagSelect');
      const styleSelect = document.getElementById('filterStyleSelect');
      const minPrice = document.getElementById('filterMinPrice');
      const maxPrice = document.getElementById('filterMaxPrice');

      state.filters.license_type = licSelect ? licSelect.value : '';
      state.filters.tag = tagSelect ? tagSelect.value : '';
      state.filters.style = styleSelect ? styleSelect.value : '';
      state.filters.min_price = minPrice ? minPrice.value.trim() : '';
      state.filters.max_price = maxPrice ? maxPrice.value.trim() : '';
      state.filters.page = 1;

      loadArtworks();
      showToast('Đã áp dụng bộ lọc tác phẩm.', 'info');
    });

    // Reset filter button
    document.getElementById('btnResetFilters')?.addEventListener('click', resetFilters);

    // Hero Explore Button
    document.getElementById('btnHeroExplore')?.addEventListener('click', () => {
      scrollToGallery();
    });

    // Mobile Menu Drawer Toggle
    const mobileMenuBtn = document.getElementById('mobileMenuToggleBtn');
    const mobileDrawerBackdrop = document.getElementById('mobileDrawerBackdrop');
    const mobileDrawerCloseBtn = document.getElementById('mobileDrawerCloseBtn');

    mobileMenuBtn?.addEventListener('click', () => {
      mobileDrawerBackdrop?.classList.add('show');
      document.body.style.overflow = 'hidden';
    });

    mobileDrawerCloseBtn?.addEventListener('click', () => {
      mobileDrawerBackdrop?.classList.remove('show');
      document.body.style.overflow = '';
    });

    mobileDrawerBackdrop?.addEventListener('click', (e) => {
      if (e.target === mobileDrawerBackdrop) {
        mobileDrawerBackdrop.classList.remove('show');
        document.body.style.overflow = '';
      }
    });

    // Global Escape Key Listener for Modals & Drawers
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeAuthModal();
        closeQuickView();
        if (mobileDrawerBackdrop) {
          mobileDrawerBackdrop.classList.remove('show');
          document.body.style.overflow = '';
        }
      }
    });

    // Search inputs handler
    const handleSearchInput = (val) => {
      const q = val.trim();
      const isHome = window.location.pathname === '/' || window.location.pathname === '';
      if (isHome) {
        state.filters.search = q;
        state.filters.page = 1;
        loadArtworks();
        scrollToGallery();
      } else if (q) {
        window.location.href = `/?q=${encodeURIComponent(q)}#gallerySection`;
      }
    };

    document.getElementById('navSearchInput')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        handleSearchInput(e.target.value);
      }
    });

    document.getElementById('mobileSearchInput')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        mobileDrawerBackdrop?.classList.remove('show');
        document.body.style.overflow = '';
        handleSearchInput(e.target.value);
      }
    });

    // Quick View Buy Button
    document.getElementById('qvBuyBtn')?.addEventListener('click', () => {
      if (state.quickViewArtwork && state.quickViewArtwork.slug) {
        const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;
        window.location.href = pUrl(`/artworks/${state.quickViewArtwork.slug}/`);
      }
    });

    // Auto-open Auth modal if ?auth=login or ?auth=register is in URL
    const urlParams = new URLSearchParams(window.location.search);
    const authAction = urlParams.get('auth');
    if (authAction === 'login') {
      openAuthModal('login');
    } else if (authAction === 'register') {
      openAuthModal('register');
    }

    // Initialize Dashboard controller if present on page
    initDashboard();
  });

  function setupPasswordToggle(btnId, inputId) {
    const btn = document.getElementById(btnId);
    const input = document.getElementById(inputId);
    if (!btn || !input) return;

    btn.addEventListener('click', () => {
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      btn.innerHTML = isPassword ? `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
          <line x1="1" y1="1" x2="23" y2="23"></line>
        </svg>
      ` : `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
          <circle cx="12" cy="12" r="3"></circle>
        </svg>
      `;
    });
  }


  // =========================================================================
  // Screen 04: Dashboard Controller (Personal Hub, Library, Orders, Withdrawals)
  // =========================================================================
  function initDashboard() {
    const dashboardRoot = document.querySelector('.dashboard-grid');
    if (!dashboardRoot) return;

    // 1. Tab Navigation
    const navItems = document.querySelectorAll('.dashboard-nav-item[data-tab]');
    const tabPanes = document.querySelectorAll('.tab-pane');

    function switchTab(targetId) {
      navItems.forEach(btn => {
        if (btn.getAttribute('data-tab') === targetId) {
          btn.classList.add('active');
        } else {
          btn.classList.remove('active');
        }
      });

      tabPanes.forEach(pane => {
        if (pane.id === targetId) {
          pane.classList.add('active');
        } else {
          pane.classList.remove('active');
        }
      });

      window.location.hash = targetId;
    }

    navItems.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.getAttribute('data-tab');
        if (targetId) switchTab(targetId);
      });
    });

    // Check URL hash on load (e.g. /dashboard/#tab-orders)
    if (window.location.hash) {
      const hashTab = window.location.hash.substring(1);
      const matched = document.getElementById(hashTab);
      if (matched && matched.classList.contains('tab-pane')) {
        switchTab(hashTab);
      }
    }

    // 2. Profile Form Update (User Me)
    const formUser = document.getElementById('formUserProfile');
    if (formUser) {
      formUser.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btnSave = document.getElementById('btnSaveUser');
        const firstName = document.getElementById('profileFirstName').value.trim();
        const lastName = document.getElementById('profileLastName').value.trim();
        const email = document.getElementById('profileEmail').value.trim();

        btnSave.disabled = true;
        btnSave.textContent = 'Đang lưu...';

        try {
          const res = await apiFetch('/api/accounts/me/', {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              first_name: firstName,
              last_name: lastName,
              email: email
            })
          });

          const data = await res.json();
          if (res.ok) {
            showToast('Cập nhật thông tin cá nhân thành công!', 'success');
            if (data.username) {
              state.currentUser = Object.assign({}, state.currentUser, data);
              hydrateDashboard(state.currentUser);
            }
          } else {
            const errStr = data.detail || (data.email ? data.email[0] : 'Không thể cập nhật thông tin.');
            showToast(errStr, 'error');
          }
        } catch (err) {
          showToast('Lỗi kết nối khi cập nhật thông tin.', 'error');
        } finally {
          btnSave.disabled = false;
          btnSave.textContent = 'Lưu thông tin cá nhân';
        }
      });
    }

    // 3. Artist Profile Form Update (Creator)
    const formArtist = document.getElementById('formArtistProfile');
    if (formArtist) {
      formArtist.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btnSave = document.getElementById('btnSaveArtist');
        const displayName = document.getElementById('artistDisplayName').value.trim();
        const bio = document.getElementById('artistBio').value.trim();
        const acceptComm = document.getElementById('artistAcceptCommission').checked;
        const avatarFile = document.getElementById('artistAvatarFile').files[0];
        const coverFile = document.getElementById('artistCoverFile').files[0];

        btnSave.disabled = true;
        btnSave.textContent = 'Đang lưu...';

        const formData = new FormData();
        formData.append('display_name', displayName);
        formData.append('bio', bio);
        formData.append('is_accepting_commissions', acceptComm);
        if (avatarFile) formData.append('avatar', avatarFile);
        if (coverFile) formData.append('cover_image', coverFile);

        try {
          const res = await apiFetch('/api/accounts/artist-profile/', {
            method: 'PATCH',
            body: formData
          });

          const data = await res.json();
          if (res.ok) {
            showToast('Cập nhật hồ sơ nghệ sĩ thành công!', 'success');
            if (state.currentUser) {
              checkCurrentUser();
            }
          } else {
            const errStr = data.detail || 'Không thể cập nhật hồ sơ nghệ sĩ.';
            showToast(errStr, 'error');
          }
        } catch (err) {
          showToast('Lỗi kết nối khi cập nhật hồ sơ.', 'error');
        } finally {
          btnSave.disabled = false;
          btnSave.textContent = 'Cập nhật hồ sơ nghệ sĩ';
        }
      });
    }

    // 3b. Dynamic Hydration for Personal Dashboard
    const mUrl = (window.ArtFairConfig && window.ArtFairConfig.mediaUrl) ? window.ArtFairConfig.mediaUrl : (p) => p;
    const pUrl = (route) => (window.ArtFairConfig && window.ArtFairConfig.pageUrl) ? window.ArtFairConfig.pageUrl(route) : route;

    async function hydrateDashboard(user) {
      const creatorFeatures = document.querySelectorAll('.creator-only-feature');

      if (!user) {
        // Guest state: Show clear message and hide creator tools
        creatorFeatures.forEach(el => el.style.display = 'none');
        const headerDisplayName = document.getElementById('dashHeaderDisplayName');
        if (headerDisplayName) headerDisplayName.textContent = 'Khách';
        const headerRolePill = document.getElementById('dashHeaderRolePill');
        if (headerRolePill) headerRolePill.innerHTML = '<span class="role-pill" style="background:#F0F0F0;color:#666;">Chưa đăng nhập</span>';
        const headerMeta = document.getElementById('dashHeaderMeta');
        if (headerMeta) headerMeta.textContent = 'Vui lòng đăng nhập để truy cập dữ liệu cá nhân';
        const headerAvatar = document.getElementById('dashHeaderAvatar');
        if (headerAvatar) headerAvatar.innerHTML = '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:var(--bg-lavender);color:var(--text-muted);font-weight:700;">?</div>';

        const libCont = document.getElementById('dashLibraryContainer');
        if (libCont) {
          libCont.innerHTML = `
            <div class="empty-state-box" style="text-align: center; padding: 64px 20px; background: #FFFFFF; border: 1px dashed var(--border-subtle); border-radius: var(--radius-lg);">
              <div style="width: 64px; height: 64px; border-radius: var(--radius-full); background: var(--bg-lavender-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--primary-berry);">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
              </div>
              <h3 style="font-family: var(--font-serif); font-size: 1.25rem; color: var(--text-plum); margin-bottom: 8px;">Vui lòng đăng nhập</h3>
              <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 20px;">
                Bạn cần đăng nhập để xem thư viện tác phẩm đã mua, đơn hàng và quản lý tài khoản cá nhân.
              </p>
              <button type="button" class="btn btn-primary" onclick="window.ArtFair && window.ArtFair.openAuthModal ? window.ArtFair.openAuthModal('login') : null" style="padding: 10px 24px;">Đăng nhập ngay</button>
            </div>
          `;
        }
        return;
      }

      // User is authenticated: populate exact user information
      const isCreator = !!(user.is_creator || user.role === 'CREATOR');
      const displayName = user.display_name || [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username;

      // Update Header
      const headerDisplayName = document.getElementById('dashHeaderDisplayName');
      if (headerDisplayName) headerDisplayName.textContent = displayName;

      const headerRolePill = document.getElementById('dashHeaderRolePill');
      if (headerRolePill) {
        headerRolePill.innerHTML = isCreator
          ? '<span class="role-pill creator">Nghệ sĩ (Creator)</span>'
          : '<span class="role-pill buyer">Người mua (Buyer)</span>';
      }

      const headerVerifiedBadge = document.getElementById('dashHeaderVerifiedBadge');
      if (headerVerifiedBadge) {
        headerVerifiedBadge.style.display = isCreator ? 'inline-flex' : 'none';
      }

      const headerMeta = document.getElementById('dashHeaderMeta');
      if (headerMeta) {
        headerMeta.innerHTML = `@${user.username} &bull; ${user.email || ''}`;
      }

      const headerAvatar = document.getElementById('dashHeaderAvatar');
      if (headerAvatar) {
        if (user.avatar) {
          headerAvatar.innerHTML = `<img src="${mUrl(user.avatar)}" alt="${user.username}" style="width: 100%; height: 100%; object-fit: cover;">`;
        } else {
          const initial = (user.username || 'U').charAt(0).toUpperCase();
          headerAvatar.innerHTML = `<div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: var(--primary-berry-light); color: var(--primary-berry); font-weight: 700; font-size: 1.4rem;">${initial}</div>`;
        }
      }

      // Update Profile Inputs
      const pLastName = document.getElementById('profileLastName');
      if (pLastName) pLastName.value = user.last_name || '';
      const pFirstName = document.getElementById('profileFirstName');
      if (pFirstName) pFirstName.value = user.first_name || '';
      const pEmail = document.getElementById('profileEmail');
      if (pEmail) pEmail.value = user.email || '';
      const pUsername = document.getElementById('profileUsername');
      if (pUsername) pUsername.textContent = `@${user.username}`;
      const pRoleDisplay = document.getElementById('profileRoleDisplay');
      if (pRoleDisplay) pRoleDisplay.textContent = isCreator ? 'Nghệ sĩ (Creator)' : 'Người mua (Buyer)';

      // Creator vs Buyer UI toggling
      creatorFeatures.forEach(el => {
        el.style.display = isCreator ? '' : 'none';
      });

      // Hydrate Creator-specific features
      if (isCreator) {
        // 1. Fetch artist profile
        try {
          const resProfile = await apiFetch('/api/accounts/artist-profile/');
          if (resProfile.ok) {
            const prof = await resProfile.json();
            const aName = document.getElementById('artistDisplayName');
            if (aName) aName.value = prof.display_name || '';
            const aBio = document.getElementById('artistBio');
            if (aBio) aBio.value = prof.bio || '';
            const aComm = document.getElementById('artistAcceptCommission');
            if (aComm) aComm.checked = !!prof.is_accepting_commissions;
          }
        } catch (_) {}

        // 2. Fetch Creator Financials & Dashboard Metrics
        try {
          const resMetrics = await apiFetch('/api/artworks/creator/dashboard-metrics/');
          if (resMetrics.ok) {
            const metrics = await resMetrics.json();
            const availBal = metrics.available_balance || 0;
            currentAvailableBalance = availBal;

            const balDisplay = document.getElementById('withdrawAvailableDisplay');
            if (balDisplay) balDisplay.textContent = availBal.toLocaleString('vi-VN') + ' VND';

            const revBal = document.getElementById('revenueAvailableBalance');
            if (revBal) revBal.textContent = availBal.toLocaleString('vi-VN') + ' ₫';

            const totalWithdrawn = document.getElementById('withdrawTotalWithdrawnDisplay');
            if (totalWithdrawn) totalWithdrawn.textContent = (metrics.total_withdrawn || 0).toLocaleString('vi-VN') + ' VND';

            const withdrawInputEl = document.getElementById('withdrawAmountInput');
            if (withdrawInputEl) withdrawInputEl.max = availBal;

            // Render withdrawals history
            if (metrics.withdrawals && metrics.withdrawals.length > 0) {
              const tbody = document.getElementById('withdrawalTableBody');
              if (tbody) {
                tbody.innerHTML = metrics.withdrawals.map(wd => `
                  <tr style="border-bottom: 1px solid var(--border-subtle);">
                    <td style="padding: 12px 10px; font-weight: 600; color: var(--text-plum);">${wd.withdrawal_code}</td>
                    <td style="padding: 12px 10px; color: var(--text-muted);">${wd.created_at ? new Date(wd.created_at).toLocaleString('vi-VN') : ''}</td>
                    <td style="padding: 12px 10px; font-weight: 700; color: var(--primary-berry);">${parseInt(wd.amount).toLocaleString('vi-VN')} VND</td>
                    <td style="padding: 12px 10px;">
                      <span style="background: #F6FFED; color: #389E0D; border: 1px solid #B7EB8F; padding: 2px 8px; border-radius: var(--radius-full); font-size: 0.78rem; font-weight: 600;">
                        ${wd.status_display || 'Đã giải ngân (Mô phỏng)'}
                      </span>
                    </td>
                    <td style="padding: 12px 10px; color: var(--text-muted); font-size: 0.82rem;">${wd.note || ''}</td>
                  </tr>
                `).join('');
              }
            }
          }
        } catch (_) {}

        // 3. Fetch Creator Commissions
        try {
          const resComm = await apiFetch('/api/commissions/?role=creator');
          if (resComm.ok) {
            const dataComm = await resComm.json();
            const commList = dataComm.results || (Array.isArray(dataComm) ? dataComm : []);
            const countHeader = document.getElementById('creatorCommissionsCountHeader');
            if (countHeader) countHeader.textContent = `Tổng cộng: ${commList.length} yêu cầu`;
            const sideCount = document.getElementById('dashSidebarCreatorCommissionsCount');
            if (sideCount) sideCount.textContent = commList.length;

            const cCont = document.getElementById('dashCreatorCommissionsContainer');
            if (cCont) {
              if (commList.length === 0) {
                cCont.innerHTML = `
                  <div class="empty-state-box" style="text-align: center; padding: 64px 20px; background: #FFFFFF; border: 1px dashed var(--border-subtle); border-radius: var(--radius-lg);">
                    <div style="width: 64px; height: 64px; border-radius: var(--radius-full); background: var(--bg-lavender-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--primary-berry);">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                    </div>
                    <h3 style="font-family: var(--font-serif); font-size: 1.25rem; color: var(--text-plum); margin-bottom: 8px;">Chưa có yêu cầu đặt vẽ nào</h3>
                    <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 20px;">
                      Bật trạng thái "Đang nhận đặt vẽ" trong phần cài đặt hồ sơ để người mua có thể gửi brief trực tiếp cho bạn.
                    </p>
                  </div>
                `;
              } else {
                cCont.innerHTML = `
                  <div class="orders-list" style="display: flex; flex-direction: column; gap: 16px;">
                    ${commList.map(comm => `
                      <div class="order-item-card" style="background: #FFFFFF; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px 24px; box-shadow: var(--shadow-sm); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                        <div style="flex: 1; min-width: 260px;">
                          <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px; flex-wrap: wrap;">
                            <span style="font-family: monospace; font-size: 0.85rem; font-weight: 700; color: var(--text-berry); background: var(--bg-lavender-subtle); padding: 2px 8px; border-radius: var(--radius-sm);">
                              ${comm.commission_code}
                            </span>
                            <span class="commission-badge status-${(comm.status || '').toLowerCase()}" style="font-size: 0.76rem; font-weight: 700; padding: 2px 10px; border-radius: var(--radius-full);">
                              ${comm.status_display || comm.status}
                            </span>
                            <span style="font-size: 0.76rem; color: var(--text-muted);">
                              ${comm.created_at ? new Date(comm.created_at).toLocaleString('vi-VN') : ''}
                            </span>
                          </div>

                          <h3 style="font-family: var(--font-serif); font-size: 1.15rem; color: var(--text-plum); margin: 0 0 6px 0; font-weight: 700;">
                            <a href="${pUrl(`/commissions/${comm.id}/`)}" style="color: inherit; text-decoration: none;">
                              ${comm.title}
                            </a>
                          </h3>

                          <div style="font-size: 0.84rem; color: var(--text-muted); display: flex; gap: 16px; flex-wrap: wrap;">
                            <span>Người đặt: <strong style="color: var(--text-plum);">@${comm.buyer ? comm.buyer.username : ''}</strong></span>
                            <span>Quyền: <strong>${comm.license_type_display || comm.license_type || ''}</strong></span>
                            <span>Hạn mong muốn: <strong>${comm.deadline ? new Date(comm.deadline).toLocaleDateString('vi-VN') : 'Thỏa thuận'}</strong></span>
                          </div>
                        </div>

                        <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 8px;">
                          <div>
                            <span style="font-size: 0.78rem; color: var(--text-muted); display: block;">Giá / Ngân sách:</span>
                            <strong style="font-size: 1.15rem; color: var(--text-berry); font-family: var(--font-serif);">
                              ${(comm.agreed_price || comm.budget || 0).toLocaleString('vi-VN')} VND
                            </strong>
                          </div>

                          <a href="${pUrl(`/commissions/${comm.id}/`)}" class="btn btn-primary btn-sm" style="text-decoration: none;">
                            Xử lý yêu cầu &rarr;
                          </a>
                        </div>
                      </div>
                    `).join('')}
                  </div>
                `;
              }
            }
          }
        } catch (_) {}
      }

      // Buyer Data (for all authenticated users)
      // 1. Library
      try {
        const resLib = await apiFetch('/api/artworks/library/my-library/');
        if (resLib.ok) {
          const dataLib = await resLib.json();
          const libItems = dataLib.results || (Array.isArray(dataLib) ? dataLib : []);
          const countLib = document.getElementById('libraryCountHeader');
          if (countLib) countLib.textContent = `Tổng cộng: ${libItems.length} tác phẩm`;
          const sideCount = document.getElementById('dashSidebarLibraryCount');
          if (sideCount) sideCount.textContent = libItems.length;

          const lCont = document.getElementById('dashLibraryContainer');
          if (lCont) {
            if (libItems.length === 0) {
              lCont.innerHTML = `
                <div class="empty-state-box" style="text-align: center; padding: 64px 20px; background: #FFFFFF; border: 1px dashed var(--border-subtle); border-radius: var(--radius-lg);">
                  <div style="width: 64px; height: 64px; border-radius: var(--radius-full); background: var(--bg-lavender-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--primary-berry);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                  </div>
                  <h3 style="font-family: var(--font-serif); font-size: 1.25rem; color: var(--text-plum); margin-bottom: 8px;">Kho tác phẩm của bạn đang trống</h3>
                  <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 20px;">
                    Bạn chưa mua quyền sử dụng tác phẩm nào. Hãy khám phá và sở hữu quyền tác phẩm số từ các nghệ sĩ Việt Nam ngay hôm nay!
                  </p>
                  <a href="${pUrl('/')}" class="btn btn-primary" style="padding: 10px 24px; text-decoration: none;">Khám phá tác phẩm ngay</a>
                </div>
              `;
            } else {
              lCont.innerHTML = `
                <div class="library-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px;">
                  ${libItems.map(item => `
                    <div class="library-card" style="background: #FFFFFF; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; box-shadow: var(--shadow-card); display: flex; flex-direction: column; transition: transform 0.2s, box-shadow 0.2s;">
                      <div style="position: relative; height: 180px; background: #FAF5FF; overflow: hidden;">
                        ${item.preview_image ? `<img src="${mUrl(item.preview_image)}" alt="${item.artwork_title}" style="width: 100%; height: 100%; object-fit: cover;">` : '<div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--text-muted);">Chưa có ảnh</div>'}
                        <span class="license-badge" style="position: absolute; top: 10px; right: 10px; font-size: 0.72rem; font-weight: 700; padding: 4px 8px; border-radius: var(--radius-full); background: rgba(46, 18, 77, 0.85); color: #FFFFFF; backdrop-filter: blur(4px);">
                          ${item.license_name || item.license_type}
                        </span>
                      </div>

                      <div style="padding: 16px; flex: 1; display: flex; flex-direction: column;">
                        <h3 style="font-family: var(--font-serif); font-size: 1.05rem; color: var(--text-plum); margin: 0 0 4px 0; font-weight: 600;">
                          ${item.artwork_title}
                        </h3>
                        <div style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 12px;">
                          Nghệ sĩ: <a href="${pUrl(`/artists/${encodeURIComponent(item.artist_username)}/`)}" style="color: var(--primary-berry); text-decoration: none; font-weight: 600;">@${item.artist_username}</a>
                        </div>

                        <div style="font-size: 0.78rem; color: var(--text-muted); background: var(--bg-lavender-subtle); padding: 8px 10px; border-radius: var(--radius-sm); margin-bottom: 14px;">
                          <div>Mã đơn: <strong style="color: var(--text-plum);">${item.order_code}</strong></div>
                          <div>Ngày mua: ${item.purchase_date ? new Date(item.purchase_date).toLocaleString('vi-VN') : ''}</div>
                        </div>

                        <div style="margin-top: auto; display: flex; flex-direction: column; gap: 8px;">
                          <div style="display: flex; gap: 8px;">
                            <a href="${pUrl(`/artworks/${item.artwork_slug}/`)}" class="btn btn-secondary btn-sm" style="flex: 1; text-align: center; text-decoration: none; padding: 6px 10px; font-size: 0.8rem;">
                              Xem trang
                            </a>
                            <button type="button" class="btn btn-primary btn-sm" onclick="window.ArtFair && window.ArtFair.downloadOriginalArtworkFile ? window.ArtFair.downloadOriginalArtworkFile(${item.artwork_id}) : null" style="flex: 1; text-align: center; padding: 6px 10px; font-size: 0.8rem;">
                              Tải tệp gốc
                            </button>
                          </div>
                          <button type="button" class="btn btn-ghost btn-sm" onclick="window.ArtFair && window.ArtFair.downloadOrderCertificate ? window.ArtFair.downloadOrderCertificate('${item.order_code}') : null" style="width: 100%; text-align: center; padding: 6px 10px; font-size: 0.8rem; border: 1px dashed var(--primary-berry); color: var(--primary-berry);">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align: -2px; margin-right: 4px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                            Xuất chứng nhận PDF
                          </button>
                        </div>
                      </div>
                    </div>
                  `).join('')}
                </div>
              `;
            }
          }
        }
      } catch (_) {}

      // 2. Favorites
      try {
        const resFav = await apiFetch('/api/artworks/favorites/my-favorites/');
        if (resFav.ok) {
          const dataFav = await resFav.json();
          const favItems = dataFav.results || (Array.isArray(dataFav) ? dataFav : []);
          const countFav = document.getElementById('favoritesCountHeader');
          if (countFav) countFav.textContent = `Tổng cộng: ${favItems.length} tác phẩm`;
          const sideCount = document.getElementById('dashSidebarFavoritesCount');
          if (sideCount) sideCount.textContent = favItems.length;

          const fCont = document.getElementById('dashFavoritesContainer');
          if (fCont) {
            if (favItems.length === 0) {
              fCont.innerHTML = `
                <div class="empty-state-box" style="text-align: center; padding: 64px 20px; background: #FFFFFF; border: 1px dashed var(--border-subtle); border-radius: var(--radius-lg);">
                  <div style="width: 64px; height: 64px; border-radius: var(--radius-full); background: var(--bg-lavender-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--primary-berry);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                  </div>
                  <h3 style="font-family: var(--font-serif); font-size: 1.25rem; color: var(--text-plum); margin-bottom: 8px;">Chưa có tác phẩm yêu thích</h3>
                  <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 20px;">
                    Hãy nhấn biểu tượng trái tim trên các tác phẩm trong sàn để lưu lại theo dõi tại đây.
                  </p>
                  <a href="${pUrl('/')}" class="btn btn-primary" style="padding: 10px 24px; text-decoration: none;">Khám phá tác phẩm</a>
                </div>
              `;
            } else {
              fCont.innerHTML = `
                <div class="favorites-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px;">
                  ${favItems.map(art => `
                    <div class="favorite-card" id="favCard_${art.id}" style="background: #FFFFFF; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; box-shadow: var(--shadow-card); display: flex; flex-direction: column;">
                      <div style="position: relative; height: 190px; background: #FAF5FF; overflow: hidden;">
                        ${art.preview_image ? `<img src="${mUrl(art.preview_image)}" alt="${art.title}" style="width: 100%; height: 100%; object-fit: cover;">` : '<div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--text-muted);">Chưa có ảnh</div>'}
                        ${art.category ? `<span style="position: absolute; top: 10px; left: 10px; font-size: 0.72rem; font-weight: 700; padding: 4px 8px; border-radius: var(--radius-full); background: rgba(255, 255, 255, 0.9); color: var(--text-plum); backdrop-filter: blur(4px);">${art.category.name}</span>` : ''}
                      </div>

                      <div style="padding: 16px; flex: 1; display: flex; flex-direction: column;">
                        <h3 style="font-family: var(--font-serif); font-size: 1.05rem; color: var(--text-plum); margin: 0 0 4px 0; font-weight: 600;">
                          <a href="${pUrl(`/artworks/${art.slug}/`)}" style="color: inherit; text-decoration: none;">${art.title}</a>
                        </h3>
                        <div style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 12px;">
                          Nghệ sĩ: <a href="${pUrl(`/artists/${encodeURIComponent(art.creator ? art.creator.username : '')}/`)}" style="color: var(--primary-berry); text-decoration: none; font-weight: 600;">@${art.creator ? art.creator.username : ''}</a>
                        </div>

                        <div style="margin-top: auto; display: flex; gap: 8px;">
                          <a href="${pUrl(`/artworks/${art.slug}/`)}" class="btn btn-primary btn-sm" style="flex: 1; text-align: center; text-decoration: none; padding: 8px;">
                            Xem chi tiết
                          </a>
                          <button type="button" class="btn btn-secondary btn-sm btn-remove-fav" data-art-id="${art.id}" style="padding: 8px 12px; color: #E11D48;" title="Xóa khỏi yêu thích">
                            ✕
                          </button>
                        </div>
                      </div>
                    </div>
                  `).join('')}
                </div>
              `;

              // Bind remove fav buttons
              fCont.querySelectorAll('.btn-remove-fav').forEach(btn => {
                btn.addEventListener('click', async () => {
                  const artId = btn.getAttribute('data-art-id');
                  try {
                    const res = await apiFetch(`/api/artworks/${artId}/favorite/`, { method: 'POST' });
                    if (res.ok) {
                      document.getElementById(`favCard_${artId}`)?.remove();
                      state.favoriteIds.delete(parseInt(artId, 10));
                      showToast('Đã xóa khỏi danh sách yêu thích.', 'info');
                    }
                  } catch (_) {}
                });
              });
            }
          }
        }
      } catch (_) {}

      // 3. Orders
      try {
        const resOrders = await apiFetch('/api/artworks/orders/my-orders/');
        if (resOrders.ok) {
          const dataOrders = await resOrders.json();
          const orderItems = dataOrders.results || (Array.isArray(dataOrders) ? dataOrders : []);
          const countOrders = document.getElementById('ordersCountHeader');
          if (countOrders) countOrders.textContent = `Tổng: ${orderItems.length} đơn`;
          const sideCount = document.getElementById('dashSidebarOrdersCount');
          if (sideCount) sideCount.textContent = orderItems.length;

          const oCont = document.getElementById('dashOrdersContainer');
          if (oCont) {
            if (orderItems.length === 0) {
              oCont.innerHTML = `
                <div class="empty-state-box" style="text-align: center; padding: 64px 20px; background: #FFFFFF; border: 1px dashed var(--border-subtle); border-radius: var(--radius-lg);">
                  <div style="width: 64px; height: 64px; border-radius: var(--radius-full); background: var(--bg-lavender-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--primary-berry);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                  </div>
                  <h3 style="font-family: var(--font-serif); font-size: 1.25rem; color: var(--text-plum); margin-bottom: 8px;">Chưa có đơn hàng nào</h3>
                  <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 20px;">
                    Các đơn mua bản quyền tác phẩm kỹ thuật số sẽ được lưu lại đầy đủ tại đây.
                  </p>
                  <a href="${pUrl('/')}" class="btn btn-primary" style="padding: 10px 24px; text-decoration: none;">Khám phá ngay</a>
                </div>
              `;
            } else {
              oCont.innerHTML = `
                <div class="orders-list" style="display: flex; flex-direction: column; gap: 16px;">
                  ${orderItems.map(order => {
                    const isCompleted = order.status === 'COMPLETED';
                    const isPending = order.status === 'PENDING';
                    const isFailed = order.status === 'FAILED';
                    const statusBadge = isCompleted
                      ? '<span style="background: #F6FFED; color: #389E0D; border: 1px solid #B7EB8F; padding: 4px 10px; border-radius: var(--radius-full); font-size: 0.8rem; font-weight: 600;">Hoàn tất thanh toán</span>'
                      : (isPending
                        ? '<span style="background: #FFF7E6; color: #D46B08; border: 1px solid #FFD591; padding: 4px 10px; border-radius: var(--radius-full); font-size: 0.8rem; font-weight: 600;">Chờ thanh toán</span>'
                        : '<span style="background: #FFF1F0; color: #CF1322; border: 1px solid #FFA39E; padding: 4px 10px; border-radius: var(--radius-full); font-size: 0.8rem; font-weight: 600;">Thanh toán thất bại</span>');

                    return `
                      <div class="order-card" style="background: #FFFFFF; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; box-shadow: var(--shadow-card);">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 14px;">
                          <div>
                            <span style="font-size: 0.8rem; color: var(--text-muted);">Mã đơn hàng:</span>
                            <strong style="font-size: 0.95rem; color: var(--text-plum); margin-left: 6px;">${order.order_code}</strong>
                            <span style="font-size: 0.8rem; color: var(--text-muted); margin-left: 12px;">Ngày tạo: ${order.created_at ? new Date(order.created_at).toLocaleString('vi-VN') : ''}</span>
                          </div>
                          <div>${statusBadge}</div>
                        </div>

                        <div style="display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
                          <div style="width: 72px; height: 72px; border-radius: var(--radius-sm); overflow: hidden; background: #FAF5FF; flex-shrink: 0;">
                            ${order.artwork && order.artwork.preview_image ? `<img src="${mUrl(order.artwork.preview_image)}" alt="${order.artwork.title}" style="width: 100%; height: 100%; object-fit: cover;">` : ''}
                          </div>
                          <div style="flex: 1; min-width: 220px;">
                            <h4 style="font-family: var(--font-serif); font-size: 1.05rem; color: var(--text-plum); margin: 0 0 4px 0;">
                              <a href="${pUrl(`/artworks/${order.artwork ? order.artwork.slug : ''}/`)}" style="color: inherit; text-decoration: none;">${order.artwork ? order.artwork.title : ''}</a>
                            </h4>
                            <div style="font-size: 0.85rem; color: var(--text-muted);">
                              Gói quyền: <strong style="color: var(--primary-berry);">${order.license_type || ''}</strong> &bull; Tác giả: @${order.artwork ? order.artwork.creator_name : ''}
                            </div>
                          </div>
                          <div style="text-align: right; min-width: 140px;">
                            <div style="font-size: 0.8rem; color: var(--text-muted);">Số tiền:</div>
                            <div style="font-family: var(--font-serif); font-size: 1.15rem; font-weight: 700; color: var(--primary-berry);">
                              ${parseInt(order.price_paid || 0).toLocaleString('vi-VN')} ₫
                            </div>
                          </div>
                        </div>

                        ${isPending || isFailed ? `
                          <div style="margin-top: 14px; display: flex; justify-content: flex-end; gap: 10px;">
                            <button type="button" class="btn btn-primary btn-sm" onclick="window.ArtFairDashboard && window.ArtFairDashboard.openPaymentRetry ? window.ArtFairDashboard.openPaymentRetry('${order.order_code}', '${(order.artwork ? order.artwork.title : '').replace(/'/g, "\\'")}', '${order.license_type}', ${parseInt(order.price_paid || 0)}) : null">
                              Thanh toán mô phỏng ngay
                            </button>
                          </div>
                        ` : (isCompleted ? `
                          <div style="margin-top: 14px; display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap;">
                            <button type="button" class="btn btn-secondary btn-sm" onclick="window.ArtFair && window.ArtFair.downloadOriginalArtworkFile ? window.ArtFair.downloadOriginalArtworkFile(${order.artwork ? order.artwork.id : 0}) : null">
                              Tải tệp gốc
                            </button>
                            <button type="button" class="btn btn-ghost btn-sm" onclick="window.ArtFair && window.ArtFair.downloadOrderCertificate ? window.ArtFair.downloadOrderCertificate('${order.order_code}') : null">
                              Xuất chứng nhận PDF
                            </button>
                          </div>
                        ` : '')}
                      </div>
                    `;
                  }).join('')}
                </div>
              `;
            }
          }
        }
      } catch (_) {}

      // 4. Buyer Commissions
      try {
        const resBComm = await apiFetch('/api/commissions/?role=buyer');
        if (resBComm.ok) {
          const dataBComm = await resBComm.json();
          const bCommList = dataBComm.results || (Array.isArray(dataBComm) ? dataBComm : []);
          const countBComm = document.getElementById('commissionsCountHeader');
          if (countBComm) countBComm.textContent = `Tổng cộng: ${bCommList.length} đơn`;
          const sideCount = document.getElementById('dashSidebarCommissionsCount');
          if (sideCount) sideCount.textContent = bCommList.length;

          const bcCont = document.getElementById('dashCommissionsContainer');
          if (bcCont) {
            if (bCommList.length === 0) {
              bcCont.innerHTML = `
                <div class="empty-state-box" style="text-align: center; padding: 64px 20px; background: #FFFFFF; border: 1px dashed var(--border-subtle); border-radius: var(--radius-lg);">
                  <div style="width: 64px; height: 64px; border-radius: var(--radius-full); background: var(--bg-lavender-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--primary-berry);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                  </div>
                  <h3 style="font-family: var(--font-serif); font-size: 1.25rem; color: var(--text-plum); margin-bottom: 8px;">Bạn chưa gửi yêu cầu đặt vẽ nào</h3>
                  <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 20px;">
                    Khám phá hồ sơ các nghệ sĩ và gửi yêu cầu sáng tạo tác phẩm độc bản theo ý tưởng của bạn.
                  </p>
                  <a href="${pUrl('/#gallerySection')}" class="btn btn-primary" style="padding: 10px 24px; text-decoration: none;">Khám phá nghệ sĩ</a>
                </div>
              `;
            } else {
              bcCont.innerHTML = `
                <div class="orders-list" style="display: flex; flex-direction: column; gap: 16px;">
                  ${bCommList.map(comm => `
                    <div class="order-item-card" style="background: #FFFFFF; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px 24px; box-shadow: var(--shadow-sm); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                      <div style="flex: 1; min-width: 260px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px; flex-wrap: wrap;">
                          <span style="font-family: monospace; font-size: 0.85rem; font-weight: 700; color: var(--text-berry); background: var(--bg-lavender-subtle); padding: 2px 8px; border-radius: var(--radius-sm);">
                            ${comm.commission_code}
                          </span>
                          <span class="commission-badge status-${(comm.status || '').toLowerCase()}" style="font-size: 0.76rem; font-weight: 700; padding: 2px 10px; border-radius: var(--radius-full);">
                            ${comm.status_display || comm.status}
                          </span>
                          <span style="font-size: 0.76rem; color: var(--text-muted);">
                            ${comm.created_at ? new Date(comm.created_at).toLocaleString('vi-VN') : ''}
                          </span>
                        </div>

                        <h3 style="font-family: var(--font-serif); font-size: 1.15rem; color: var(--text-plum); margin: 0 0 6px 0; font-weight: 700;">
                          <a href="${pUrl(`/commissions/${comm.id}/`)}" style="color: inherit; text-decoration: none;">
                            ${comm.title}
                          </a>
                        </h3>

                        <div style="font-size: 0.84rem; color: var(--text-muted); display: flex; gap: 16px; flex-wrap: wrap;">
                          <span>Nghệ sĩ: <a href="${pUrl(`/artists/${encodeURIComponent(comm.creator ? comm.creator.username : '')}/`)}" style="color: var(--text-berry); font-weight: 600; text-decoration: none;">@${comm.creator ? comm.creator.username : ''}</a></span>
                          <span>Quyền: <strong>${comm.license_type_display || comm.license_type || ''}</strong></span>
                          <span>Hạn bàn giao: <strong>${comm.deadline ? new Date(comm.deadline).toLocaleDateString('vi-VN') : 'Thỏa thuận'}</strong></span>
                        </div>
                      </div>

                      <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 8px;">
                        <div>
                          <span style="font-size: 0.78rem; color: var(--text-muted); display: block;">Giá / Ngân sách:</span>
                          <strong style="font-size: 1.15rem; color: var(--text-berry); font-family: var(--font-serif);">
                            ${(comm.agreed_price || comm.budget || 0).toLocaleString('vi-VN')} ₫
                          </strong>
                        </div>

                        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                          <a href="${pUrl(`/commissions/${comm.id}/`)}" class="btn btn-secondary btn-sm" style="text-decoration: none;">
                            Chi tiết & Tiến độ &rarr;
                          </a>
                        </div>
                      </div>
                    </div>
                  `).join('')}
                </div>
              `;
            }
          }
        }
      } catch (_) {}

      // 5. Notifications
      try {
        const resNotif = await apiFetch('/api/accounts/notifications/');
        if (resNotif.ok) {
          const dataNotif = await resNotif.json();
          const notifs = dataNotif.results || (Array.isArray(dataNotif) ? dataNotif : []);
          const nCont = document.getElementById('dashNotificationsContainer');
          if (nCont) {
            if (notifs.length === 0) {
              nCont.innerHTML = `
                <div class="empty-state-box" style="text-align: center; padding: 64px 20px; background: #FFFFFF; border: 1px dashed var(--border-subtle); border-radius: var(--radius-lg);">
                  <div style="width: 64px; height: 64px; border-radius: var(--radius-full); background: var(--bg-lavender-subtle); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--primary-berry);">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
                  </div>
                  <h3 style="font-family: var(--font-serif); font-size: 1.25rem; color: var(--text-plum); margin-bottom: 8px;">Bạn không có thông báo mới</h3>
                  <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 440px; margin: 0 auto 20px;">
                    Mọi cập nhật về trạng thái đơn hàng, thanh toán và đặt vẽ sẽ hiển thị tại đây.
                  </p>
                </div>
              `;
            } else {
              nCont.innerHTML = `
                <div class="notifications-dashboard-list" style="display: flex; flex-direction: column; gap: 12px;">
                  ${notifs.map(n => `
                    <div class="notification-card-item ${!n.is_read ? 'unread' : ''}" id="dashNotif_${n.id}" style="background: ${!n.is_read ? '#FFF9FB' : '#FFFFFF'}; border: 1px solid ${!n.is_read ? 'rgba(197, 42, 112, 0.25)' : 'var(--border-subtle)'}; border-radius: var(--radius-md); padding: 18px 20px; box-shadow: var(--shadow-sm); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                      <div style="flex: 1; min-width: 260px;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                          ${!n.is_read ? '<span style="width: 8px; height: 8px; border-radius: 50%; background: #E11D48; display: inline-block;"></span>' : ''}
                          <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--text-plum); margin: 0;">${n.title}</h4>
                          <span style="font-size: 0.75rem; color: var(--text-muted);">${n.created_at ? new Date(n.created_at).toLocaleString('vi-VN') : ''}</span>
                        </div>
                        <p style="margin: 0; font-size: 0.88rem; color: var(--text-plum); line-height: 1.5;">${n.message}</p>
                      </div>
                      <div style="display: flex; gap: 8px; align-items: center;">
                        ${n.target_url ? `
                          <a href="${pUrl(n.target_url)}" class="btn btn-primary btn-sm" style="text-decoration: none; font-size: 0.8rem;">
                            Xem chi tiết &rarr;
                          </a>
                        ` : ''}
                        ${!n.is_read ? `
                          <button type="button" class="btn btn-ghost btn-sm btn-mark-dash-read" data-notif-id="${n.id}" style="font-size: 0.78rem;">
                            Đã đọc
                          </button>
                        ` : ''}
                      </div>
                    </div>
                  `).join('')}
                </div>
              `;

              nCont.querySelectorAll('.btn-mark-dash-read').forEach(btn => {
                btn.addEventListener('click', async () => {
                  const notifId = btn.getAttribute('data-notif-id');
                  try {
                    await apiFetch(`/api/accounts/notifications/${notifId}/mark-read/`, { method: 'POST' });
                    const card = document.getElementById(`dashNotif_${notifId}`);
                    if (card) {
                      card.classList.remove('unread');
                      card.style.background = '#FFFFFF';
                      card.style.borderColor = 'var(--border-subtle)';
                      btn.remove();
                    }
                  } catch (_) {}
                });
              });
            }
          }
        }
      } catch (_) {}
    }

    if (state.currentUser) {
      hydrateDashboard(state.currentUser);
    }
    window.addEventListener('artfair:user_loaded', (e) => {
      hydrateDashboard(e.detail);
    });

    // 4. Withdrawal Controller
    let currentAvailableBalance = 0;
    const balanceElem = document.getElementById('withdrawAvailableDisplay');
    if (balanceElem) {
      const match = balanceElem.textContent.replace(/[^0-9]/g, '');
      currentAvailableBalance = parseInt(match, 10) || 0;
    }

    const withdrawInput = document.getElementById('withdrawAmountInput');
    const withdrawConfirmModal = document.getElementById('withdrawConfirmModal');

    window.ArtFairDashboard = window.ArtFairDashboard || {};

    window.ArtFairDashboard.setQuickAmount = function(pct) {
      if (!withdrawInput) return;
      const amt = Math.floor(currentAvailableBalance * pct);
      withdrawInput.value = amt > 0 ? amt : 0;
    };

    const btnOpenConfirm = document.getElementById('btnOpenWithdrawConfirm');
    if (btnOpenConfirm) {
      btnOpenConfirm.addEventListener('click', () => {
        const amt = parseInt(withdrawInput.value, 10);
        if (!amt || amt <= 0) {
          showToast('Vui lòng nhập số tiền rút hợp lệ (> 0 VND).', 'error');
          return;
        }
        if (amt > currentAvailableBalance) {
          showToast('Số tiền rút vượt quá số dư khả dụng.', 'error');
          return;
        }

        const confirmDisplay = document.getElementById('modalWithdrawAmountConfirm');
        if (confirmDisplay) confirmDisplay.textContent = amt.toLocaleString('vi-VN') + ' VND';
        withdrawConfirmModal.style.display = 'flex';
      });
    }

    window.ArtFairDashboard.closeWithdrawModal = function() {
      if (withdrawConfirmModal) withdrawConfirmModal.style.display = 'none';
    };

    const btnSubmitWithdraw = document.getElementById('btnSubmitWithdrawFinal');
    if (btnSubmitWithdraw) {
      btnSubmitWithdraw.addEventListener('click', async () => {
        const amt = parseInt(withdrawInput.value, 10);
        const note = document.getElementById('withdrawNoteInput').value.trim();

        btnSubmitWithdraw.disabled = true;
        btnSubmitWithdraw.textContent = 'Đang xử lý...';

        try {
          const res = await apiFetch('/api/artworks/creator/withdrawals/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ amount: amt, note: note })
          });

          const data = await res.json();
          if (res.ok) {
            showToast(data.detail || 'Yêu cầu rút tiền mô phỏng thành công!', 'success');
            window.ArtFairDashboard.closeWithdrawModal();

            // Update UI balances
            currentAvailableBalance = data.new_available_balance;
            if (balanceElem) balanceElem.textContent = currentAvailableBalance.toLocaleString('vi-VN') + ' VND';
            const revElem = document.getElementById('revenueAvailableBalance');
            if (revElem) revElem.textContent = currentAvailableBalance.toLocaleString('vi-VN') + ' VND';
            const totalWithdrawnElem = document.getElementById('withdrawTotalWithdrawnDisplay');
            if (totalWithdrawnElem && data.total_withdrawn) {
              totalWithdrawnElem.textContent = data.total_withdrawn.toLocaleString('vi-VN') + ' VND';
            }

            // Append row to table
            const tbody = document.getElementById('withdrawalTableBody');
            if (tbody && data.withdrawal) {
              const wd = data.withdrawal;
              const tr = document.createElement('tr');
              tr.style.borderBottom = '1px solid var(--border-subtle)';
              tr.innerHTML = `
                <td style="padding: 12px 10px; font-weight: 600; color: var(--text-plum);">${wd.withdrawal_code}</td>
                <td style="padding: 12px 10px; color: var(--text-muted);">${new Date().toLocaleString('vi-VN')}</td>
                <td style="padding: 12px 10px; font-weight: 700; color: var(--primary-berry);">${parseInt(wd.amount).toLocaleString('vi-VN')} VND</td>
                <td style="padding: 12px 10px;">
                  <span style="background: #F6FFED; color: #389E0D; border: 1px solid #B7EB8F; padding: 2px 8px; border-radius: var(--radius-full); font-size: 0.78rem; font-weight: 600;">
                    ${wd.status_display || 'Đã giải ngân (Mô phỏng)'}
                  </span>
                </td>
                <td style="padding: 12px 10px; color: var(--text-muted); font-size: 0.82rem;">${wd.note || ''}</td>
              `;
              tbody.insertBefore(tr, tbody.firstChild);
            }
            withdrawInput.value = '';
          } else {
            showToast(data.detail || 'Không thể thực hiện yêu cầu rút tiền.', 'error');
          }
        } catch (err) {
          showToast('Lỗi kết nối khi gửi yêu cầu rút tiền.', 'error');
        } finally {
          btnSubmitWithdraw.disabled = false;
          btnSubmitWithdraw.textContent = 'Xác nhận rút ngay';
        }
      });
    }

    // 5. Retry Payment Controller for Orders Tab
    let activeRetryOrderCode = null;
    const retryModal = document.getElementById('retryPaymentModal');

    window.ArtFairDashboard.openPaymentRetry = function(orderCode, title, license, price) {
      activeRetryOrderCode = orderCode;
      document.getElementById('retryModalOrderCode').textContent = orderCode;
      document.getElementById('retryModalTitle').textContent = title;
      document.getElementById('retryModalLicense').textContent = license;
      document.getElementById('retryModalPrice').textContent = price.toLocaleString('vi-VN') + ' VND';
      if (retryModal) retryModal.style.display = 'flex';
    };

    window.ArtFairDashboard.closeRetryPaymentModal = function() {
      if (retryModal) retryModal.style.display = 'none';
      activeRetryOrderCode = null;
    };

    // Modal backdrop click and Escape listeners for dashboard modals
    if (withdrawConfirmModal) {
      withdrawConfirmModal.addEventListener('click', (e) => {
        if (e.target === withdrawConfirmModal) window.ArtFairDashboard.closeWithdrawModal();
      });
    }
    if (retryModal) {
      retryModal.addEventListener('click', (e) => {
        if (e.target === retryModal) window.ArtFairDashboard.closeRetryPaymentModal();
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (withdrawConfirmModal && withdrawConfirmModal.style.display !== 'none') {
          window.ArtFairDashboard.closeWithdrawModal();
        }
        if (retryModal && retryModal.style.display !== 'none') {
          window.ArtFairDashboard.closeRetryPaymentModal();
        }
      }
    });

    window.ArtFairDashboard.executeRetryPayment = async function(action) {
      if (!activeRetryOrderCode) return;
      try {
        const res = await apiFetch(`/api/artworks/orders/${activeRetryOrderCode}/simulate-payment/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ action: action })
        });

        const data = await res.json();
        if (res.ok) {
          showToast(data.detail || 'Thao tác thanh toán hoàn tất!', action === 'SUCCESS' ? 'success' : 'info');
          window.ArtFairDashboard.closeRetryPaymentModal();
          setTimeout(() => {
            window.location.reload();
          }, 800);
        } else {
          showToast(data.detail || 'Thanh toán không thành công.', 'error');
        }
      } catch (err) {
        showToast('Lỗi kết nối cổng thanh toán mô phỏng.', 'error');
      }
    };
  }

  // Export initDashboard to ArtFair namespace
  window.ArtFair.initDashboard = initDashboard;

})();
