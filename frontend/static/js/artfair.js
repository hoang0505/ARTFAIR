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
      const res = await fetch('/api/accounts/auth/csrf/', { credentials: 'same-origin' });
      if (res.ok) {
        const data = await res.json();
        if (data.csrf_token) {
          syncCsrfToken(data.csrf_token);
        }
      }
    } catch (_) {}
    return getCsrfToken();
  }

  // Centralized API Request Wrapper with CSRF protection and Friendly Notice
  async function apiFetch(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = Object.assign({}, options.headers || {});

    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const token = getCsrfToken();
      if (token && !headers['X-CSRFToken']) {
        headers['X-CSRFToken'] = token;
      }
    }

    const fetchOptions = {
      ...options,
      method,
      headers,
      credentials: options.credentials || 'same-origin'
    };

    try {
      const res = await fetch(url, fetchOptions);

      // Check for CSRF failure
      if (res.status === 403) {
        const clone = res.clone();
        try {
          const bodyText = await clone.text();
          if (bodyText.includes('CSRF') || bodyText.includes('Csrftoken') || bodyText.includes('csrf')) {
            console.warn('[ARTFAIR CSRF Mismatch] Request to', url, 'failed CSRF check. Re-syncing token...');
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
    getCsrfToken: getCsrfToken,
    syncCsrfToken: syncCsrfToken,
    fetchCsrfToken: fetchCsrfToken,
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
    }
  };

  // 1. Initialize CSRF token from live cookie or meta tag
  function initCsrfToken() {
    getCsrfToken();
  }

  // 2. Check current authenticated user session
  async function checkCurrentUser() {
    try {
      const res = await fetch('/api/accounts/me/', { credentials: 'same-origin' });
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
  }

  // Notification Helpers
  async function loadNotifications() {
    try {
      const res = await fetch('/api/accounts/notifications/', { credentials: 'same-origin' });
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
          window.location.href = notif.link_url;
        }
      });
    });
  }

  async function markNotificationAsRead(id) {
    try {
      const res = await fetch(`/api/accounts/notifications/${id}/read/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': state.csrfToken || getCookie('csrftoken') || ''
        },
        credentials: 'same-origin'
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
      const res = await fetch('/api/accounts/notifications/mark-all-read/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': state.csrfToken || getCookie('csrftoken') || ''
        },
        credentials: 'same-origin'
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
      const res = await fetch('/api/artworks/favorites/ids/', { credentials: 'same-origin' });
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
      const res = await fetch(`/api/artworks/${artId}/favorite/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': state.csrfToken || getCookie('csrftoken') || ''
        },
        credentials: 'same-origin'
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

    if (state.currentUser) {
      const user = state.currentUser;
      const isCreator = user.role === 'CREATOR';
      const displayName = (user.artist_profile && user.artist_profile.display_name) 
        ? user.artist_profile.display_name 
        : (user.username || 'Người dùng');
      const avatarUrl = (user.artist_profile && user.artist_profile.avatar) 
        ? user.artist_profile.avatar 
        : '';
      const initial = displayName.charAt(0).toUpperCase();

      if (authContainer) {
        authContainer.innerHTML = `
          ${isCreator ? `
            <a href="/studio/" class="btn btn-secondary btn-sm" id="navBtnCreatorStudio" style="text-decoration:none; display:inline-flex; align-items:center; gap:6px; font-weight:700; color:var(--primary-berry); border-color:var(--primary-berry); padding:6px 14px; border-radius:var(--radius-full); margin-right:4px;" title="Vào Creator Studio để quản lý và đăng bán tranh">
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
                <a href="/dashboard/#tab-notifications">Xem tất cả thông báo &rarr;</a>
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
              
              <a href="/dashboard/" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                <span>Khu vực cá nhân</span>
              </a>

              <a href="/dashboard/#tab-favorites" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                <span>Tác phẩm yêu thích</span>
              </a>

              <a href="/dashboard/#tab-notifications" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
                <span>Thông báo của tôi</span>
              </a>

              ${isCreator ? `
                <div class="dropdown-divider"></div>
                <div style="padding: 6px 12px 2px; font-size: 0.72rem; text-transform: uppercase; font-weight: 700; color: var(--primary-berry); letter-spacing: 0.5px;">Quản lý Nghệ sĩ</div>

                <a href="/artists/${encodeURIComponent(user.username)}/" class="dropdown-item" style="text-decoration:none; color:inherit; font-weight: 600;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                  <span>Hồ sơ nghệ sĩ của tôi</span>
                </a>

                <a href="/studio/" class="dropdown-item" style="text-decoration:none; color:inherit; font-weight: 600; color: var(--primary-berry);">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                  <span>Studio / Quản lý tác phẩm</span>
                </a>

                <a href="/studio/?open=publish" class="dropdown-item" style="text-decoration:none; color:inherit;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                  <span>Đăng tác phẩm mới</span>
                </a>

                <a href="/dashboard/#tab-creator-commissions" class="dropdown-item" style="text-decoration:none; color:inherit;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                  <span>Yêu cầu đặt vẽ nhận được</span>
                </a>

                <a href="/dashboard/#tab-revenue" class="dropdown-item" style="text-decoration:none; color:inherit;">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                  <span>Doanh thu & Rút tiền mô phỏng</span>
                </a>

                <div class="dropdown-divider"></div>
                <div style="padding: 6px 12px 2px; font-size: 0.72rem; text-transform: uppercase; font-weight: 700; color: var(--text-muted); letter-spacing: 0.5px;">Mua sắm & Sở hữu</div>
              ` : `
                <div class="dropdown-divider"></div>
              `}

              <a href="/dashboard/#tab-library" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                <span>Tác phẩm đã mua</span>
              </a>

              <a href="/dashboard/#tab-orders" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                <span>${isCreator ? 'Đơn mua tác phẩm' : 'Đơn hàng của tôi'}</span>
              </a>

              <a href="/dashboard/#tab-commissions" class="dropdown-item" style="text-decoration:none; color:inherit;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                <span>Yêu cầu đặt vẽ đã gửi</span>
              </a>

              <div class="dropdown-divider"></div>

              <a href="/settings/" class="dropdown-item" style="text-decoration:none; color:inherit;">
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
            <a href="/dashboard/" class="mobile-nav-link">Khu vực cá nhân</a>
            <a href="/dashboard/#tab-favorites" class="mobile-nav-link">Tác phẩm yêu thích</a>
            <a href="/dashboard/#tab-notifications" class="mobile-nav-link">Thông báo của tôi</a>
            ${isCreator ? `
              <a href="/artists/${encodeURIComponent(user.username)}/" class="mobile-nav-link" style="color: var(--primary-berry); font-weight: 700;">Hồ sơ nghệ sĩ của tôi</a>
              <a href="/studio/" class="mobile-nav-link" style="color: var(--primary-berry); font-weight: 700;">Studio / Quản lý tác phẩm</a>
              <a href="/studio/?open=publish" class="mobile-nav-link">Đăng tác phẩm mới</a>
              <a href="/dashboard/#tab-creator-commissions" class="mobile-nav-link">Yêu cầu đặt vẽ nhận được</a>
              <a href="/dashboard/#tab-revenue" class="mobile-nav-link">Doanh thu & Rút tiền</a>
            ` : ''}
            <a href="/dashboard/#tab-library" class="mobile-nav-link">Tác phẩm đã mua</a>
            <a href="/dashboard/#tab-orders" class="mobile-nav-link">Đơn hàng</a>
            <a href="/dashboard/#tab-commissions" class="mobile-nav-link">Yêu cầu đặt vẽ đã gửi</a>
            <a href="/settings/" class="mobile-nav-link">Cài đặt tài khoản</a>
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
    const loginAlert = document.getElementById('loginAlert');
    const registerAlert = document.getElementById('registerAlert');
    if (loginAlert) {
      loginAlert.className = 'form-alert';
      loginAlert.textContent = '';
    }
    if (registerAlert) {
      registerAlert.className = 'form-alert';
      registerAlert.textContent = '';
    }
  }

  // 4. Handle Login Form Submit
  async function handleLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('btnLoginSubmit');
    const alertBox = document.getElementById('loginAlert');
    const usernameInput = document.getElementById('loginUsername');
    const passwordInput = document.getElementById('loginPassword');

    const username = usernameInput?.value.trim();
    const password = passwordInput?.value;

    if (!username || !password) {
      showAlert(alertBox, 'Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.', 'error');
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
        if (data.csrf_token) {
          syncCsrfToken(data.csrf_token);
        } else {
          getCsrfToken();
        }
        showToast('Đăng nhập thành công!', 'success');
        closeAuthModal();
        await checkCurrentUser();
        window.dispatchEvent(new CustomEvent('artfair:login_success', { detail: data }));

        // Handle returnUrl / next parameter safely (prevent external open-redirects)
        const urlParams = new URLSearchParams(window.location.search);
        const nextUrl = urlParams.get('next');
        if (nextUrl && nextUrl.startsWith('/') && !nextUrl.startsWith('//')) {
          setTimeout(() => { window.location.href = nextUrl; }, 350);
          return;
        }

        // Reload if on protected server-rendered views
        if (window.location.pathname.startsWith('/studio') ||
            window.location.pathname.startsWith('/dashboard') ||
            window.location.pathname.startsWith('/settings') ||
            window.location.pathname.startsWith('/commissions/')) {
          setTimeout(() => { window.location.reload(); }, 350);
        }
      } else {
        const errorMsg = data.detail || (data.non_field_errors && data.non_field_errors[0]) || 'Đăng nhập không thành công. Vui lòng kiểm tra lại.';
        showAlert(alertBox, errorMsg, 'error');
      }
    } catch (err) {
      showAlert(alertBox, 'Không thể kết nối đến máy chủ. Vui lòng thử lại.', 'error');
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
    const btn = document.getElementById('btnRegisterSubmit');
    const alertBox = document.getElementById('registerAlert');
    const usernameInput = document.getElementById('regUsername');
    const emailInput = document.getElementById('regEmail');
    const passwordInput = document.getElementById('regPassword');
    const confirmPasswordInput = document.getElementById('regConfirmPassword');
    const agreeTermsInput = document.getElementById('regAgreeTerms');
    const roleInput = document.querySelector('input[name="regRole"]:checked');

    const username = usernameInput?.value.trim();
    const email = emailInput?.value.trim();
    const password = passwordInput?.value;
    const confirmPassword = confirmPasswordInput?.value;
    const agreeTerms = agreeTermsInput ? agreeTermsInput.checked : true;
    const role = roleInput ? roleInput.value : 'BUYER';

    if (!username || !email || !password) {
      showAlert(alertBox, 'Vui lòng điền đầy đủ các thông tin đăng ký.', 'error');
      return;
    }

    if (confirmPasswordInput && password !== confirmPassword) {
      showAlert(alertBox, 'Mật khẩu xác nhận không khớp. Vui lòng kiểm tra lại.', 'error');
      return;
    }

    if (agreeTermsInput && !agreeTerms) {
      showAlert(alertBox, 'Vui lòng đánh dấu đồng ý với Điều khoản dịch vụ và Chính sách bảo mật.', 'error');
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
        if (data.csrf_token) {
          syncCsrfToken(data.csrf_token);
        } else {
          getCsrfToken();
        }
        showToast('Tạo tài khoản thành công! Đang tự động đăng nhập...', 'success');
        
        // Auto-login after successful registration
        try {
          const loginRes = await apiFetch('/api/accounts/auth/login/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username, password })
          });
          if (loginRes.ok) {
            const loginData = await loginRes.json().catch(() => ({}));
            if (loginData.csrf_token) syncCsrfToken(loginData.csrf_token);
            closeAuthModal();
            await checkCurrentUser();
            window.dispatchEvent(new CustomEvent('artfair:login_success', { detail: { username } }));

            const urlParams = new URLSearchParams(window.location.search);
            const nextUrl = urlParams.get('next');
            if (nextUrl && nextUrl.startsWith('/') && !nextUrl.startsWith('//')) {
              setTimeout(() => { window.location.href = nextUrl; }, 350);
              return;
            }

            // If creator registered, redirect to Studio
            if (role === 'CREATOR') {
              setTimeout(() => { window.location.href = '/studio/'; }, 400);
              return;
            }

            if (window.location.pathname.startsWith('/studio') ||
                window.location.pathname.startsWith('/dashboard') ||
                window.location.pathname.startsWith('/settings')) {
              setTimeout(() => { window.location.reload(); }, 350);
            }
            return;
          }
        } catch (_) {}

        // Fallback: switch to login tab and preserve username
        switchAuthTab('login');
        const loginUser = document.getElementById('loginUsername');
        if (loginUser) loginUser.value = username;
        showAlert(document.getElementById('loginAlert'), 'Tài khoản đã tạo thành công. Vui lòng đăng nhập.', 'success');

      } else {
        let msg = 'Đăng ký không thành công:\n';
        if (data.username) msg += `• Tên đăng nhập: ${data.username.join(', ')}\n`;
        if (data.email) msg += `• Email: ${data.email.join(', ')}\n`;
        if (data.password) msg += `• Mật khẩu: ${data.password.join(', ')}\n`;
        if (data.detail) msg += `• ${data.detail}\n`;
        showAlert(alertBox, msg, 'error');
      }
    } catch (err) {
      showAlert(alertBox, 'Không thể kết nối đến máy chủ. Vui lòng thử lại.', 'error');
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
      state.currentUser = null;
      renderNavbarAuth();
      showToast('Đã đăng xuất khỏi tài khoản.', 'info');

      // If user was on protected pages, redirect to home page
      if (window.location.pathname.startsWith('/dashboard') || 
          window.location.pathname.startsWith('/studio') || 
          window.location.pathname.startsWith('/settings') ||
          window.location.pathname.startsWith('/commissions/')) {
        setTimeout(() => { window.location.href = '/'; }, 300);
      }
    } catch (err) {
      showToast('Lỗi kết nối khi đăng xuất.', 'error');
    }
  }

  function showAlert(elem, msg, type = 'error') {
    if (!elem) return;
    elem.className = `form-alert show ${type}`;
    elem.innerText = msg;
  }

  // 7. Load Categories & Tags
  async function loadTaxonomies() {
    try {
      const [catRes, tagRes] = await Promise.all([
        fetch('/api/artworks/categories/'),
        fetch('/api/artworks/tags/')
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
      const res = await fetch(`/api/artworks/?${params.toString()}`);
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
      const artistProfileUrl = artistUsername ? `/artists/${encodeURIComponent(artistUsername)}/` : null;
      const artistHtml = artistProfileUrl
        ? `<a href="${artistProfileUrl}" class="art-card-artist-link" onclick="event.stopPropagation();">${artistName}</a>`
        : artistName;
      const categoryName = art.category ? art.category.name : '';
      const previewSrc = art.preview_image || '';

      html += `
        <article class="art-card" data-artwork-id="${art.id}">
          <div class="art-card-img-wrap">
            <img class="art-card-img protected-artwork-img" src="${previewSrc}" alt="${art.title}" loading="lazy" draggable="false">
            <div style="position: absolute; top: 10px; left: 10px; display: flex; flex-direction: column; gap: 4px; z-index: 2;">
              <span class="art-card-status-badge">Đang bán</span>
              ${categoryName ? `<span class="art-card-badge">${categoryName}</span>` : ''}
              ${art.style ? `<span class="art-card-style-badge">${art.style}</span>` : ''}
            </div>
            <button class="art-card-favorite-btn ${isFav ? 'active' : ''}" data-artwork-id="${art.id}" title="${isFav ? 'Bỏ lưu yêu thích' : 'Yêu thích'}">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="${isFav ? '#E11D48' : 'none'}" stroke="${isFav ? '#E11D48' : 'currentColor'}" stroke-width="2">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
              </svg>
            </button>
          </div>
          <div class="art-card-body">
            <h3 class="art-card-title" title="${art.title}">${art.title}</h3>
            <div class="art-card-artist">${artistHtml}</div>
            <div class="art-card-price-row">
              <span class="art-card-price">${formattedPrice}</span>
              <span class="art-card-license-hint">${licenses.length} gói quyền</span>
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
        if (artObj && artObj.slug) {
          window.location.href = `/artworks/${artObj.slug}/`;
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

    const imgElem = document.getElementById('qvImage');
    const titleElem = document.getElementById('qvTitle');
    const artistElem = document.getElementById('qvArtist');
    const categoryElem = document.getElementById('qvCategory');
    const tagsElem = document.getElementById('qvTags');
    const descElem = document.getElementById('qvDesc');
    const tiersElem = document.getElementById('qvLicenseTiers');

    if (imgElem) imgElem.src = art.preview_image || '';
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
          window.location.href = `/artworks/${art.slug}/`;
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
        window.location.href = `/artworks/${state.quickViewArtwork.slug}/`;
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
              state.currentUser = data;
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
