#!/usr/bin/env python3
"""
patch_android_storage.py - Migración de almacenamiento interno a externo para Godot 4 Android

Este script automatiza la migración de rutas de almacenamiento interno (user://)
a almacenamiento externo (/storage/emulated/0/smb1r.android/) para el proyecto
"Super Mario Bros. Remastered" (SMB1R).

Autor: Retired64
Versión: 1.0
"""

import os
import re
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

# === CONFIGURACIÓN DE COLORES ===
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    
    @classmethod
    def disable(cls):
        cls.RESET = cls.RED = cls.GREEN = cls.YELLOW = ""
        cls.BLUE = cls.MAGENTA = cls.CYAN = cls.BOLD = ""


# === CONFIGURACIÓN DEL PROYECTO ===
EXTERNAL_STORAGE_BASE = "/storage/emulated/0/smb1r.android"
BACKUP_DIR = "backups"
LOG_PREFIX = "patch_log"


# === ESTRUCTURAS DE DATOS ===
@dataclass
class Change:
    line_number: int
    description: str
    old_value: str = ""
    new_value: str = ""


@dataclass
class FileResult:
    filepath: str
    success: bool
    changes: list = field(default_factory=list)
    error: Optional[str] = None
    backup_path: Optional[str] = None


# === CLASE PRINCIPAL ===
class AndroidStoragePatcher:
    def __init__(self, project_root: Path, dry_run: bool = False, verbose: bool = True):
        self.project_root = project_root
        self.dry_run = dry_run
        self.verbose = verbose
        self.results: list[FileResult] = []
        self.log_lines: list[str] = []
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = project_root / BACKUP_DIR / self.timestamp
        
    def log(self, msg: str, color: str = "", to_file: bool = True):
        if self.verbose:
            print(f"{color}{msg}{Colors.RESET}")
        if to_file:
            self.log_lines.append(re.sub(r'\033\[[0-9;]*m', '', msg))
    
    def log_success(self, msg: str): self.log(f"[✓] {msg}", Colors.GREEN)
    def log_warning(self, msg: str): self.log(f"[⚠] {msg}", Colors.YELLOW)
    def log_error(self, msg: str): self.log(f"[✗] {msg}", Colors.RED)
    def log_info(self, msg: str): self.log(f"[•] {msg}", Colors.CYAN)
    
    def is_comment_line(self, line: str) -> bool:
        return line.strip().startswith('#')
    
    def validate_project(self) -> bool:
        project_file = self.project_root / "project.godot"
        if not project_file.exists():
            self.log_error(f"No se encontró project.godot en {self.project_root}")
            return False
        self.log_success(f"Proyecto Godot válido: {self.project_root}")
        return True
    
    def create_backup(self, filepath: Path) -> Optional[Path]:
        if not filepath.exists():
            return None
        if self.dry_run:
            self.log_info(f"  [DRY-RUN] Backup: {filepath.name}")
            return filepath.with_suffix(filepath.suffix + '.backup')
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        rel_path = filepath.relative_to(self.project_root)
        backup_path = self.backup_dir / rel_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filepath, backup_path)
        return backup_path
    
    def save_log(self):
        suffix = "_dryrun" if self.dry_run else ""
        log_path = self.project_root / f"{LOG_PREFIX}_{self.timestamp}{suffix}.txt"
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"Patch Android Storage Log - {datetime.now().isoformat()}\n")
            f.write("=" * 60 + "\n\n")
            f.write("\n".join(self.log_lines))
        self.log_info(f"Log guardado en: {log_path}")
    
    def verify_patches(self) -> tuple[bool, list[str]]:
        """Verifica que no quedan referencias user:// problemáticas."""
        remaining = []
        patterns = [
            r'"user://saves["/]',
            r'"user://achievements\.sav"',
            r'"user://marathon_recordings["/]',
            r'"user://mod_configs["/]',
            r'"user://settings\.cfg"',
            r'"user://baserom\.nes"',
            r'"user://rom_pointer\.smb"',
            r'"user://resource_packs["/]',
        ]
        combined = '|'.join(patterns)
        
        for gd_file in self.project_root.rglob("*.gd"):
            try:
                content = gd_file.read_text(encoding='utf-8')
                for i, line in enumerate(content.split('\n'), 1):
                    if not self.is_comment_line(line) and re.search(combined, line):
                        rel = gd_file.relative_to(self.project_root)
                        remaining.append(f"{rel}:{i}")
            except Exception:
                pass
        
        for tscn_file in self.project_root.rglob("*.tscn"):
            try:
                content = tscn_file.read_text(encoding='utf-8')
                if re.search(combined, content):
                    rel = tscn_file.relative_to(self.project_root)
                    remaining.append(str(rel))
            except Exception:
                pass
        
        return (len(remaining) == 0, remaining)
    
    # === PATCHES ESPECÍFICOS ===
    
    def patch_export_presets(self) -> FileResult:
        filepath = self.project_root / "export_presets.cfg"
        result = FileResult(filepath=str(filepath), success=False)
        
        if not filepath.exists():
            result.error = "Archivo no encontrado"
            return result
        
        result.backup_path = str(self.create_backup(filepath))
        content = filepath.read_text(encoding='utf-8')
        lines = content.split('\n')
        new_lines, changes = [], []
        
        patterns = [
            (r'^(\s*permissions/manage_external_storage\s*=\s*)false\s*$', 'true', 'manage_external_storage'),
            (r'^(\s*permissions/read_external_storage\s*=\s*)false\s*$', 'true', 'read_external_storage'),
            (r'^(\s*permissions/write_external_storage\s*=\s*)false\s*$', 'true', 'write_external_storage'),
        ]
        
        for i, line in enumerate(lines, 1):
            new_line = line
            for pattern, repl, name in patterns:
                m = re.match(pattern, line)
                if m:
                    new_line = f"{m.group(1)}{repl}"
                    changes.append(Change(i, f"{name} = {repl}"))
                    break
            new_lines.append(new_line)
        
        if changes and not self.dry_run:
            filepath.write_text('\n'.join(new_lines), encoding='utf-8')
        
        result.success, result.changes = True, changes
        return result
    
    def patch_global_gd(self) -> FileResult:
        filepath = self.project_root / "Scripts/Classes/Singletons/Global.gd"
        result = FileResult(filepath=str(filepath), success=False)
        
        if not filepath.exists():
            result.error = "Archivo no encontrado"
            return result
        
        result.backup_path = str(self.create_backup(filepath))
        content = filepath.read_text(encoding='utf-8')
        changes = []
        
        replacements = [
            (r'(const\s+ROM_POINTER_PATH\s*:=\s*)"user://rom_pointer\.smb"',
             f'\\1"{EXTERNAL_STORAGE_BASE}/rom_pointer.smb"', "ROM_POINTER_PATH"),
            (r'(const\s+ROM_PATH\s*:=\s*)"user://baserom\.nes"',
             f'\\1"{EXTERNAL_STORAGE_BASE}/baserom.nes"', "ROM_PATH"),
            (r'(const\s+ROM_ASSETS_PATH\s*:=\s*)"user://resource_packs/BaseAssets"',
             f'\\1"{EXTERNAL_STORAGE_BASE}/resource_packs/BaseAssets"', "ROM_ASSETS_PATH"),
        ]
        
        new_content = content
        for pattern, repl, name in replacements:
            m = re.search(pattern, new_content)
            if m:
                line_num = new_content[:m.start()].count('\n') + 1
                new_content = re.sub(pattern, repl, new_content)
                changes.append(Change(line_num, f"{name} actualizado"))
        
        if changes and not self.dry_run:
            filepath.write_text(new_content, encoding='utf-8')
        
        result.success, result.changes = True, changes
        return result
    
    def patch_settings_manager(self) -> FileResult:
        filepath = self.project_root / "Scripts/Classes/Singletons/SettingsManager.gd"
        result = FileResult(filepath=str(filepath), success=False)
        
        if not filepath.exists():
            result.error = "Archivo no encontrado"
            return result
        
        result.backup_path = str(self.create_backup(filepath))
        content = filepath.read_text(encoding='utf-8')
        changes = []
        
        replacements = [
            (r'(const\s+SETTINGS_DIR\s*:=\s*)"user://settings\.cfg"',
             f'\\1"{EXTERNAL_STORAGE_BASE}/settings.cfg"', "SETTINGS_DIR"),
            (r'DirAccess\.make_dir_absolute\s*\(\s*"user://resource_packs"\s*\)',
             f'DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}/resource_packs")',
             "make_dir resource_packs"),
        ]
        
        new_content = content
        for pattern, repl, desc in replacements:
            m = re.search(pattern, new_content)
            if m:
                line_num = new_content[:m.start()].count('\n') + 1
                new_content = re.sub(pattern, repl, new_content)
                changes.append(Change(line_num, f"{desc} actualizado"))
        
        if changes and not self.dry_run:
            filepath.write_text(new_content, encoding='utf-8')
        
        result.success, result.changes = True, changes
        return result
    
    def patch_mod_loader_path(self) -> FileResult:
        filepath = self.project_root / "addons/mod_loader/internal/path.gd"
        result = FileResult(filepath=str(filepath), success=False)
        
        if not filepath.exists():
            result.error = "Archivo no encontrado"
            return result
        
        result.backup_path = str(self.create_backup(filepath))
        content = filepath.read_text(encoding='utf-8')
        changes = []
        
        pattern = r'(const\s+MOD_CONFIG_DIR_PATH\s*:=\s*)"user://mod_configs"'
        m = re.search(pattern, content)
        if m:
            line_num = content[:m.start()].count('\n') + 1
            new_content = re.sub(pattern, f'\\1"{EXTERNAL_STORAGE_BASE}/mod_configs"', content)
            changes.append(Change(line_num, "MOD_CONFIG_DIR_PATH actualizado"))
            if not self.dry_run:
                filepath.write_text(new_content, encoding='utf-8')
        
        result.success, result.changes = True, changes
        return result
    
    def patch_save_manager(self) -> FileResult:
        """Modifica SaveManager.gd - INCLUYE SAVE_DIR línea 3."""
        filepath = self.project_root / "Scripts/Classes/Singletons/SaveManager.gd"
        result = FileResult(filepath=str(filepath), success=False)
        
        if not filepath.exists():
            result.error = "Archivo no encontrado"
            return result
        
        result.backup_path = str(self.create_backup(filepath))
        content = filepath.read_text(encoding='utf-8')
        original = content
        changes = []
        
        # ORDEN IMPORTANTE: Patrones más específicos primero
        replacements = [
            # 1. CRÍTICO: Constante SAVE_DIR (línea 3)
            (r'(const\s+SAVE_DIR\s*:=\s*)"user://saves/CAMPAIGN\.sav"',
             f'\\1"{EXTERNAL_STORAGE_BASE}/saves/CAMPAIGN.sav"', "SAVE_DIR constante"),
            # 2. DirAccess.make_dir_recursive_absolute (línea 73)
            (r'DirAccess\.make_dir_recursive_absolute\s*\(\s*"user://saves"\s*\)',
             f'DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}/saves")',
             "make_dir saves"),
            # 3. Rutas con barra final
            (r'"user://saves/"', f'"{EXTERNAL_STORAGE_BASE}/saves/"', "saves/"),
            # 4. Rutas sin barra (lookahead negativo para no duplicar)
            (r'"user://saves"(?!/)', f'"{EXTERNAL_STORAGE_BASE}/saves"', "saves"),
            # 5. Achievements
            (r'"user://achievements\.sav"', f'"{EXTERNAL_STORAGE_BASE}/achievements.sav"', "achievements.sav"),
            # 6. Marathon recordings
            (r'"user://marathon_recordings/"', f'"{EXTERNAL_STORAGE_BASE}/marathon_recordings/"', "marathon_recordings/"),
            (r'"user://marathon_recordings"(?!/)', f'"{EXTERNAL_STORAGE_BASE}/marathon_recordings"', "marathon_recordings"),
        ]
        
        for pattern, repl, desc in replacements:
            for m in re.finditer(pattern, content):
                line_start = content.rfind('\n', 0, m.start()) + 1
                line_end = content.find('\n', m.start())
                line_content = content[line_start:line_end if line_end != -1 else len(content)]
                if not self.is_comment_line(line_content):
                    line_num = content[:m.start()].count('\n') + 1
                    changes.append(Change(line_num, f"{desc} actualizado"))
            content = re.sub(pattern, repl, content)
        
        if content != original and not self.dry_run:
            filepath.write_text(content, encoding='utf-8')
        
        result.success, result.changes = True, changes
        return result
    
    def patch_resource_pack_loader(self) -> FileResult:
        """Modifica ResourcePackLoader.gd - NUEVO en v1.2.0."""
        filepath = self.project_root / "Scripts/Parts/ResourcePackLoader.gd"
        result = FileResult(filepath=str(filepath), success=False)
        
        if not filepath.exists():
            result.error = "Archivo no encontrado (opcional)"
            result.success = True  # No es crítico si no existe
            return result
        
        result.backup_path = str(self.create_backup(filepath))
        content = filepath.read_text(encoding='utf-8')
        original = content
        changes = []
        
        replacements = [
            # Ruta con barra
            (r'"user://resource_packs/"', f'"{EXTERNAL_STORAGE_BASE}/resource_packs/"', "resource_packs/"),
            # Ruta sin barra (para shell_show_in_file_manager y get_directories_at)
            (r'"user://resource_packs"(?!/)', f'"{EXTERNAL_STORAGE_BASE}/resource_packs"', "resource_packs"),
        ]
        
        for pattern, repl, desc in replacements:
            for m in re.finditer(pattern, content):
                line_num = content[:m.start()].count('\n') + 1
                changes.append(Change(line_num, f"{desc} actualizado"))
            content = re.sub(pattern, repl, content)
        
        if content != original and not self.dry_run:
            filepath.write_text(content, encoding='utf-8')
        
        result.success, result.changes = True, changes
        return result
    
    def patch_tscn_files(self) -> list[FileResult]:
        """Busca y modifica archivos .tscn con referencias user://."""
        results = []
        pattern = r'"user://(saves|achievements|marathon_recordings|mod_configs|resource_packs)[^"]*"'
        
        for tscn_file in self.project_root.rglob("*.tscn"):
            try:
                content = tscn_file.read_text(encoding='utf-8')
                if not re.search(pattern, content):
                    continue
                
                result = FileResult(filepath=str(tscn_file), success=False)
                result.backup_path = str(self.create_backup(tscn_file))
                changes = []
                
                replacements = [
                    (r'"user://saves/"', f'"{EXTERNAL_STORAGE_BASE}/saves/"'),
                    (r'"user://saves"(?!/)', f'"{EXTERNAL_STORAGE_BASE}/saves"'),
                    (r'"user://achievements\.sav"', f'"{EXTERNAL_STORAGE_BASE}/achievements.sav"'),
                    (r'"user://marathon_recordings/"', f'"{EXTERNAL_STORAGE_BASE}/marathon_recordings/"'),
                    (r'"user://marathon_recordings"(?!/)', f'"{EXTERNAL_STORAGE_BASE}/marathon_recordings"'),
                    (r'"user://mod_configs/"', f'"{EXTERNAL_STORAGE_BASE}/mod_configs/"'),
                    (r'"user://mod_configs"(?!/)', f'"{EXTERNAL_STORAGE_BASE}/mod_configs"'),
                    (r'"user://resource_packs/"', f'"{EXTERNAL_STORAGE_BASE}/resource_packs/"'),
                    (r'"user://resource_packs"(?!/)', f'"{EXTERNAL_STORAGE_BASE}/resource_packs"'),
                ]
                
                new_content = content
                for pat, repl in replacements:
                    for m in re.finditer(pat, new_content):
                        line_num = new_content[:m.start()].count('\n') + 1
                        changes.append(Change(line_num, "Referencia user:// actualizada"))
                    new_content = re.sub(pat, repl, new_content)
                
                if changes and not self.dry_run:
                    tscn_file.write_text(new_content, encoding='utf-8')
                
                result.success, result.changes = True, changes
                results.append(result)
                
            except Exception as e:
                results.append(FileResult(str(tscn_file), False, error=str(e)))
        
        return results
    
    def run(self) -> bool:
        self.log("")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.RESET}", to_file=False)
        self.log(f"{Colors.BOLD}  Patch Android Storage - SMB1R v1.2.0{Colors.RESET}", to_file=False)
        self.log(f"{Colors.BOLD}{'='*60}{Colors.RESET}", to_file=False)
        self.log("")
        
        if self.dry_run:
            self.log_warning("MODO DRY-RUN: No se realizarán cambios reales\n")
        
        if not self.validate_project():
            return False
        
        self.log("")
        self.log_info("Iniciando proceso de parcheo...\n")
        
        # Lista de patches (INCLUYE ResourcePackLoader.gd)
        patches = [
            ("export_presets.cfg", self.patch_export_presets),
            ("Global.gd", self.patch_global_gd),
            ("SettingsManager.gd", self.patch_settings_manager),
            ("ModLoader path.gd", self.patch_mod_loader_path),
            ("SaveManager.gd", self.patch_save_manager),
            ("ResourcePackLoader.gd", self.patch_resource_pack_loader),
        ]
        
        for name, patch_func in patches:
            self.log(f"{Colors.BOLD}Archivo: {name}{Colors.RESET}")
            try:
                result = patch_func()
                self.results.append(result)
                self._print_result(result)
            except Exception as e:
                self.log_error(f"Error: {e}")
                self.results.append(FileResult(name, False, error=str(e)))
            self.log("")
        
        # Archivos TSCN
        self.log(f"{Colors.BOLD}Buscando archivos .tscn...{Colors.RESET}")
        tscn_results = self.patch_tscn_files()
        if tscn_results:
            for r in tscn_results:
                self.results.append(r)
                rel = Path(r.filepath).relative_to(self.project_root)
                self.log(f"\n{Colors.BOLD}TSCN: {rel}{Colors.RESET}")
                self._print_result(r)
        else:
            self.log_info("No se encontraron archivos .tscn para actualizar.")
        
        # Verificación post-patch
        if not self.dry_run:
            self.log("")
            self.log(f"{Colors.BOLD}Verificando cambios...{Colors.RESET}")
            verified, remaining = self.verify_patches()
            if verified:
                self.log_success("Todas las referencias actualizadas correctamente")
            else:
                self.log_warning(f"{len(remaining)} referencias pendientes:")
                for ref in remaining[:10]:
                    self.log(f"    - {ref}", Colors.YELLOW)
                if len(remaining) > 10:
                    self.log(f"    ... y {len(remaining) - 10} más", Colors.YELLOW)
        
        self._print_summary()
        self.save_log()
        return all(r.success for r in self.results)
    
    def _print_result(self, result: FileResult):
        if result.error:
            self.log_error(f"Error: {result.error}")
            return
        if not result.changes:
            self.log_warning("No se encontraron cambios")
            return
        for c in result.changes:
            self.log(f"    - Línea {c.line_number}: {c.description}", Colors.CYAN)
        action = "detectados" if self.dry_run else "aplicados"
        self.log_success(f"Total: {len(result.changes)} cambios {action}")
    
    def _print_summary(self):
        self.log("")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        self.log(f"{Colors.BOLD}  RESUMEN{Colors.RESET}")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        
        total = len(self.results)
        ok = sum(1 for r in self.results if r.success)
        changes = sum(len(r.changes) for r in self.results if r.success)
        
        self.log(f"  • Archivos procesados: {ok}/{total}", Colors.CYAN)
        self.log(f"  • Total de cambios: {changes}", Colors.CYAN)
        
        if not self.dry_run and any(r.backup_path for r in self.results):
            self.log(f"  • Backups en: {self.backup_dir}", Colors.CYAN)
        
        failed = [r for r in self.results if not r.success]
        if failed:
            self.log("")
            self.log_warning("Archivos con errores:")
            for r in failed:
                self.log(f"    - {r.filepath}: {r.error}", Colors.RED)
        
        # ACCIÓN MANUAL REQUERIDA
        self.log("")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        self.log(f"{Colors.BOLD}  ⚠ ACCIÓN MANUAL REQUERIDA{Colors.RESET}")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        self.log("")
        self.log_warning("Añade este código en Global.gd (_ready o _enter_tree):")
        self.log("")
        code = f'''func _ready():
    if OS.get_name() == "Android":
        OS.request_permissions()
        # Crear directorios
        DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}")
        DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}/saves")
        DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}/mods")
        DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}/mod_configs")
        DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}/resource_packs")
        DirAccess.make_dir_recursive_absolute("{EXTERNAL_STORAGE_BASE}/marathon_recordings")'''
        for line in code.split('\n'):
            self.log(f"    {line}", Colors.MAGENTA)
        self.log("")


class RollbackManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.backup_base = project_root / BACKUP_DIR
    
    def list_backups(self) -> list[Path]:
        if not self.backup_base.exists():
            return []
        return sorted([d for d in self.backup_base.iterdir() if d.is_dir()], reverse=True)
    
    def rollback(self, backup_dir: Optional[Path] = None) -> bool:
        backups = self.list_backups()
        if not backups:
            print(f"{Colors.RED}[✗] No hay backups{Colors.RESET}")
            return False
        
        if backup_dir is None:
            backup_dir = backups[0]
            print(f"{Colors.CYAN}[•] Usando: {backup_dir.name}{Colors.RESET}")
        
        if not backup_dir.exists():
            print(f"{Colors.RED}[✗] No existe: {backup_dir}{Colors.RESET}")
            return False
        
        restored = 0
        for bf in backup_dir.rglob("*"):
            if bf.is_file():
                rel = bf.relative_to(backup_dir)
                target = self.project_root / rel
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(bf, target)
                    print(f"{Colors.GREEN}[✓] {rel}{Colors.RESET}")
                    restored += 1
                except Exception as e:
                    print(f"{Colors.RED}[✗] {rel}: {e}{Colors.RESET}")
        
        print(f"\n{Colors.GREEN}[✓] {restored} archivos restaurados{Colors.RESET}")
        return True


def find_project_root() -> Optional[Path]:
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "project.godot").exists():
            return parent
    return None


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except:
            Colors.disable()
    
    parser = argparse.ArgumentParser(
        description="Migra almacenamiento interno a externo para SMB1R Android",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python patch_android_storage.py              # Aplicar cambios
  python patch_android_storage.py --dry-run    # Ver sin aplicar
  python patch_android_storage.py --verify     # Verificar estado
  python patch_android_storage.py --rollback   # Restaurar backup
  python patch_android_storage.py --list-backups
        """
    )
    
    parser.add_argument("--dry-run", "-n", action="store_true", help="Ver cambios sin aplicar")
    parser.add_argument("--rollback", "-r", action="store_true", help="Restaurar backup")
    parser.add_argument("--list-backups", "-l", action="store_true", help="Listar backups")
    parser.add_argument("--verify", "-v", action="store_true", help="Verificar referencias")
    parser.add_argument("--project-dir", "-p", type=Path, help="Directorio del proyecto")
    parser.add_argument("--quiet", "-q", action="store_true", help="Salida mínima")
    
    args = parser.parse_args()
    
    project_root = args.project_dir.resolve() if args.project_dir else find_project_root()
    if not project_root:
        print(f"{Colors.RED}[✗] No se encontró project.godot{Colors.RESET}")
        sys.exit(1)
    
    if args.list_backups:
        mgr = RollbackManager(project_root)
        backups = mgr.list_backups()
        if not backups:
            print(f"{Colors.YELLOW}[⚠] No hay backups{Colors.RESET}")
        else:
            print(f"{Colors.BOLD}Backups disponibles:{Colors.RESET}")
            for b in backups:
                print(f"  • {b.name}")
        sys.exit(0)
    
    if args.rollback:
        mgr = RollbackManager(project_root)
        sys.exit(0 if mgr.rollback() else 1)
    
    if args.verify:
        patcher = AndroidStoragePatcher(project_root, dry_run=True, verbose=True)
        print(f"{Colors.BOLD}Verificando referencias user://...{Colors.RESET}\n")
        verified, remaining = patcher.verify_patches()
        if verified:
            print(f"{Colors.GREEN}[✓] No hay referencias user:// problemáticas{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}[⚠] {len(remaining)} referencias pendientes:{Colors.RESET}")
            for ref in remaining:
                print(f"    - {ref}")
        sys.exit(0 if verified else 1)
    
    patcher = AndroidStoragePatcher(project_root, args.dry_run, not args.quiet)
    sys.exit(0 if patcher.run() else 1)


if __name__ == "__main__":
    main()
