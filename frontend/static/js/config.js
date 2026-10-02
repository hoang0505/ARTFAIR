/**
 * ARTFAIR Client Configuration
 * Single source of truth for runtime environment detection & API endpoints.
 * Automatically adapts between Local development and GitHub Pages production.
 */
(function (window) {
  'use strict';

  const hostname = window.location.hostname;
  const isGitHubPages = hostname.endsWith('github.io');
  const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0';

  // Base Path: GitHub Pages deploys under repository name path: /ARTFAIR/
  let basePath = '/';
  if (isGitHubPages) {
    basePath = '/ARTFAIR/';
  } else if (window.location.pathname.startsWith('/ARTFAIR/')) {
    basePath = '/ARTFAIR/';
  }

  // Backend API URL:
  // On GitHub Pages: connect directly to live PythonAnywhere backend
  // On Localhost: use relative /api/ (same-origin Django server) or custom local host
  let apiBaseUrl = '';
  let mediaBaseUrl = '';

  if (isGitHubPages) {
    apiBaseUrl = 'https://hoang0505.pythonanywhere.com';
    mediaBaseUrl = 'https://hoang0505.pythonanywhere.com';
  }

  // Allow developer override via localStorage if needed
  try {
    const customApi = window.localStorage.getItem('artfair_custom_api');
    if (customApi) apiBaseUrl = customApi;
  } catch (_) {}

  const ArtFairConfig = {
    isGitHubPages: isGitHubPages,
    isLocalhost: isLocalhost,
    BASE_PATH: basePath,
    API_BASE_URL: apiBaseUrl,
    MEDIA_BASE_URL: mediaBaseUrl,

    /**
     * Resolves an API endpoint to a full URL (absolute or relative)
     */
    apiUrl: function (endpoint) {
      if (!endpoint) return apiBaseUrl;
      if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) return endpoint;
      if (!endpoint.startsWith('/')) endpoint = '/' + endpoint;
      return apiBaseUrl + endpoint;
    },

    /**
     * Resolves a page route taking into account the base path (/ARTFAIR/ or /)
     */
    pageUrl: function (route) {
      if (!route || route === '/' || route === '') {
        return basePath;
      }
      if (route.startsWith('http://') || route.startsWith('https://')) return route;
      // Strip leading slash
      const cleanRoute = route.replace(/^\/+/, '');
      return basePath + cleanRoute;
    },

    /**
     * Resolves media file URLs (previews, avatars, covers)
     */
    mediaUrl: function (path) {
      if (!path) return '';
      if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('data:')) {
        return path;
      }
      if (!path.startsWith('/')) path = '/' + path;
      return mediaBaseUrl + path;
    }
  };

  window.ArtFairConfig = ArtFairConfig;
})(window);
