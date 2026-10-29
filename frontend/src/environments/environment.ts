export const environment = {
  production: false,
  apiBaseUrl: '/api/v1',
  /**
   * Distribución de la app Android "Andrómeda".
   * Publica el APK y define aquí la URL para habilitar la descarga en /andromeda.
   * Ejemplo: apkUrl: '/static/andromeda/andromeda-1.0.0.apk'.
   */
  andromeda: {
    apkUrl: '',
    version: '',
    sizeMb: 0,
    updatedAt: '',
    minAndroid: '8.0',
  },
};
