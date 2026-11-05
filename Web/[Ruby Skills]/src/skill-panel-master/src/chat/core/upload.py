import os, uuid, shutil, zipfile, json


def load_skill(file, upload_folder, skills_dir):
    """Extract ZIP, validate manifest, run validation.
    Returns (zip_path, extract_dir, manifest, skill_md, list_of_py_contents, error_reason).
    All 6 values are always populated (None or str/list).

    Ограничения безопасности:
    - MAX_DEPTH: макс. глубина вложенности (3 уровня до strip)
    - MAX_FILES: макс. количество файлов (50)
    - MAX_FILE_SIZE: макс. размер одного файла (10 МБ)
    - MAX_EXTRACTED_SIZE: макс. общий размер (50 МБ)
    """
    MAX_DEPTH = 3
    MAX_FILES = 10
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    MAX_EXTRACTED_SIZE = 50 * 1024 * 1024  # 50 MB

    zip_id = str(uuid.uuid4())
    zip_path = os.path.join(upload_folder, f"{zip_id}.zip")
    file.save(zip_path)

    extract_dir = os.path.join(upload_folder, zip_id)
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            namelist = zf.namelist()

            # Limit: total files count
            if len(namelist) > MAX_FILES:
                shutil.rmtree(extract_dir, ignore_errors=True)
                return None, None, None, None, None, \
                    f"Слишком много файлов в архиве (максимум {MAX_FILES})"

            # Validate and sanitize paths
            inner_files = []
            for name in namelist:
                # Skip directories and empty entries
                if not name or name.endswith('/'):
                    continue

                # Skip macOS resource forks and metadata
                if name.startswith('__MACOSX') or name.startswith('.__'):
                    continue

                # Security: block path traversal
                if '..' in name:
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    return None, None, None, None, None, \
                        "Обнаружена попытка path traversal"

                raw_parts = name.split('/')
                parts = [p for p in raw_parts if p and not p.startswith('.')]
                if not parts:
                    continue

                # Security: block absolute paths
                if os.path.isabs(parts[-1]) or '\\' in name:
                    continue

                if len(parts) > MAX_DEPTH:
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    return None, None, None, None, None, \
                        "Слишком глубокая вложенность файлов в архиве"

                file_info = zf.getinfo(name)
                # Security: file size limit
                if file_info.file_size > MAX_FILE_SIZE:
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    return None, None, None, None, None, \
                        f"Файл '{name}' слишком большой (макс. 10 МБ)"

                inner_files.append({"parts": parts, "orig_name": name, "file_info": file_info})

            if not inner_files:
                shutil.rmtree(extract_dir, ignore_errors=True)
                return None, None, None, None, None, "В архиве нет допустимых файлов"

            # Check total extracted size
            total_size = sum(f["file_info"].file_size for f in inner_files)
            if total_size > MAX_EXTRACTED_SIZE:
                shutil.rmtree(extract_dir, ignore_errors=True)
                return None, None, None, None, None, \
                    f"Архив слишком большой (макс. 50 МБ)"

            # Determine root directory to strip (if all files share one common top-level dir)
            root_dirs = set(f["parts"][0] for f in inner_files)
            strip_root = len(root_dirs) == 1

            extract_count = 0
            for finfo in inner_files:
                parts = list(finfo["parts"])  # make a copy

                if strip_root:
                    parts = parts[1:]

                if not parts:
                    continue

                dest_path = os.path.join(extract_dir, *parts)

                # Security: verify resolved path is inside extract_dir
                real_dest = os.path.realpath(dest_path)
                real_extract = os.path.realpath(extract_dir)
                if not real_dest.startswith(real_extract + os.sep) and real_dest != real_extract:
                    continue

                # Check depth after strip (max 2 levels for skill files)
                if len(parts) > 2:
                    continue

                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with zf.open(finfo["orig_name"]) as src:
                    with open(dest_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                extract_count += 1

            if extract_count == 0:
                shutil.rmtree(extract_dir, ignore_errors=True)
                return None, None, None, None, None, "Не удалось извлечь файлы из архива"

    except zipfile.BadZipFile:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None, None, None, None, None, "ZIP архив повреждён или не является корректным ZIP файлом"
    except Exception as e:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None, None, None, None, None, f"Ошибка при извлечении архива: {e}"

    manifest_path = os.path.join(extract_dir, 'manifest.json')
    if not os.path.exists(manifest_path):
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None, None, None, None, None, "В архиве не найден manifest.json"

    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except Exception:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None, None, None, None, None, "manifest.json не содержит валидный JSON"

    # Read skill.md (case-insensitive)
    skill_md = ""
    for root, dirs, files in os.walk(extract_dir):
        for fname in files:
            if fname.lower() == 'skill.md':
                skill_md_path = os.path.join(root, fname)
                try:
                    with open(skill_md_path, 'r', encoding='utf-8') as f:
                        skill_md = f.read()
                except Exception:
                    pass
                break
        if skill_md:
            break

    # Collect all .py files
    py_contents = []
    for root, dirs, files in os.walk(extract_dir):
        for fname in files:
            if fname.endswith('.py'):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        py_contents.append(f.read())
                except Exception:
                    pass

    return zip_path, extract_dir, manifest, skill_md, py_contents, None
