@echo off
REM ============================================================
REM  Entrenamiento del modelo CSI2PointCloud (6 clases) - 1 paso
REM  Doble clic para: entrenar -> evaluar (test) -> visualizar.
REM ============================================================
setlocal

REM --- Ajustar estas rutas en la PC de la universidad si hace falta ---
if "%CSI2PC_REPO%"=="" set CSI2PC_REPO=%~dp0csi2pointcloud
if "%CSI2PC_DATA%"=="" set CSI2PC_DATA=%~dp0mmfi_dataset
if "%CSI2PC_OUT%"==""  set CSI2PC_OUT=%~dp0pc\resultados

echo ============================================================
echo  REPO modelo : %CSI2PC_REPO%
echo  DATOS       : %CSI2PC_DATA%
echo  RESULTADOS  : %CSI2PC_OUT%
echo ============================================================

echo.
echo [1/3] Entrenando (60 epocas, split 70/15/15 por accion)...
python "%~dp0pc\entrenar_v2.py" 60
if errorlevel 1 goto :error

echo.
echo [2/3] Metricas ICP sobre el TEST...
python "%~dp0pc\test.py"
if errorlevel 1 goto :error

echo.
echo [3/3] Visualizacion GT vs predicho (colores de Maata)...
python "%~dp0pc\vis_matta.py"
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  LISTO. Revisa la carpeta de resultados:
echo    %CSI2PC_OUT%
echo    - curva_perdida.png  - pred_vs_gt.png
echo    - metricas_test.txt  - modelo\csi2pc_v2.pth
echo ============================================================
pause
exit /b 0

:error
echo.
echo *** Hubo un error. Revisa que Python, las librerias (requirements.txt)
echo *** y las rutas CSI2PC_REPO / CSI2PC_DATA sean correctas.
pause
exit /b 1
