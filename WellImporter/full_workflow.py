# -*- coding: utf-8 -*-

import csv
import json
import zipfile
from datetime import datetime
from pathlib import Path

from .severity import Severity


class FullWorkflowManager:
    """Формирует итоговый отчёт и резервную копию полного рабочего цикла."""

    def __init__(self, project, preflight_checker):
        self.project = project
        self.preflight = preflight_checker

    def write_report(self, output_dir, summary):
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = output / f"WellImporter_FullWorkflow_{stamp}.json"
        csv_path = output / f"WellImporter_FullWorkflow_Errors_{stamp}.csv"

        json_path.write_text(
            json.dumps(self._json_safe(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        audit = summary.get("audit_after", {}) or {}
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow([
                "Серьёзность", "Категория", "Номер скважины", "Слой", "FID", "Описание"
            ])
            for issue in audit.get("issues", []):
                writer.writerow([
                    Severity.label(issue.get("severity")),
                    issue.get("category", ""),
                    issue.get("number", ""),
                    issue.get("layer_name", ""),
                    issue.get("feature_id", ""),
                    issue.get("message", ""),
                ])

        return {"json": str(json_path), "csv": str(csv_path)}

    def create_backup(self, output_dir, report_files=None):
        """Архивирует QGIS-проект и существующие локальные внешние ресурсы."""
        project_file = str(self.project.fileName() or "")
        if not project_file:
            raise Exception("Перед резервным копированием QGIS-проект должен быть сохранён.")

        project_path = Path(project_file)
        if not project_path.is_file():
            raise Exception(f"Файл QGIS-проекта не найден: {project_path}")

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = output / f"WellImporter_Backup_{stamp}.zip"

        resources = [
            item for item in self.preflight.check_external_files()
            if item.get("exists") and Path(item.get("path", "")).is_file()
        ]
        seen = {str(project_path.resolve())}
        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "project": project_path.name,
            "resources": [],
            "reports": [],
        }

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(project_path, f"project/{project_path.name}")
            for index, item in enumerate(resources, start=1):
                source = Path(item["path"])
                try:
                    resolved = str(source.resolve())
                except Exception:
                    resolved = str(source)
                if resolved in seen or source == archive_path:
                    continue
                seen.add(resolved)
                member = f"data/{index:03d}_{source.name}"
                archive.write(source, member)
                manifest["resources"].append({
                    "original": str(source),
                    "archive": member,
                    "source": item.get("source", ""),
                })

            for report in report_files or []:
                report_path = Path(report)
                if report_path.is_file():
                    member = f"reports/{report_path.name}"
                    archive.write(report_path, member)
                    manifest["reports"].append(member)

            archive.writestr(
                "WellImporter_BACKUP_MANIFEST.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )

        return {
            "path": str(archive_path),
            "resources": len(manifest["resources"]),
            "reports": len(manifest["reports"]),
        }

    def _json_safe(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        if hasattr(value, "__dict__"):
            return self._json_safe(value.__dict__)
        return str(value)
