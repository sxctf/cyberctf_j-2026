package main

import (
	"encoding/xml"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

type socialArchive struct {
	XMLName xml.Name `xml:"socialArchive"`
	Profile struct {
		Handle      string `xml:"handle"`
		DisplayName string `xml:"displayName"`
		Network     string `xml:"network"`
		Risk        string `xml:"risk"`
	} `xml:"profile"`
}

type legacyEntity struct {
	Name        string
	IsParameter bool
	Value       string
	SystemID    string
}

var (
	systemEntityRE = regexp.MustCompile(`(?is)<!ENTITY\s+(%?)\s*([A-Za-z0-9_.:-]+)\s+SYSTEM\s+['"]([^'"]+)['"]\s*>`)
	valueEntityRE  = regexp.MustCompile(`(?is)<!ENTITY\s+(%?)\s*([A-Za-z0-9_.:-]+)\s+['"]([^'"]*)['"]\s*>`)
	paramRefRE     = regexp.MustCompile(`%([A-Za-z0-9_.:-]+);`)
	htmlPercentRE  = regexp.MustCompile(`(?i)&#x25;|&#37;`)
)

// main подключает статический фронтенд и legacy endpoint импорта архивов,
// после чего запускает HTTP-сервер задания на порту 8080.
func main() {
	rand.Seed(time.Now().UnixNano())

	mux := http.NewServeMux()
	mux.HandleFunc("/api/archive/import", handleArchiveImport)
	mux.Handle("/", http.FileServer(http.Dir(".")))

	addr := ":8080"
	log.Printf("PulseMirror backend listening on http://localhost%s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

// handleArchiveImport - единая публичная точка импорта архивов. Обычный UI
// делает GET для получения legacy XML-архива; задуманный путь атаки меняет
// запрос на POST с XML-телом.
func handleArchiveImport(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		handleArchiveFetch(w, r)
	case http.MethodPost:
		handleArchivePost(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
}

// handleArchiveFetch возвращает штатный XML-документ SocialVault. Так игрок
// узнает XML declaration, Content-Type и структуру тегов через перехват трафика,
// а не через явные подсказки в интерфейсе.
func handleArchiveFetch(w http.ResponseWriter, r *http.Request) {
	if r.URL.Query().Get("id") != "sv-7142" {
		http.Error(w, "archive bundle not found", http.StatusNotFound)
		return
	}

	params := map[string]string{
		"handle":      "@mira_ops",
		"displayName": "Mira Operations",
		"network":     "Chatter",
		"risk":        "low",
	}

	w.Header().Set("Content-Type", "application/xml; charset=utf-8")
	_, _ = w.Write([]byte(buildArchiveXML(params)))
}

// handleArchivePost принимает вручную отправленный legacy XML-архив и ставит
// его в фоновую обработку. В ответ возвращается только статус job, поэтому
// результат раскрытия entity напрямую игроку не отражается.
func handleArchivePost(w http.ResponseWriter, r *http.Request) {
	contentType := r.Header.Get("Content-Type")
	if !strings.Contains(contentType, "xml") {
		http.Error(w, "legacy importer expects XML", http.StatusUnsupportedMediaType)
		return
	}

	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
	if err != nil {
		http.Error(w, "archive body too large", http.StatusBadRequest)
		return
	}

	document := string(body)
	if strings.TrimSpace(document) == "" {
		http.Error(w, "empty archive body", http.StatusBadRequest)
		return
	}

	go processArchive(document)

	w.Header().Set("Content-Type", "application/json")
	_, _ = fmt.Fprintf(w, `{"jobId":"imp_%06x","status":"queued","message":"Archive accepted for background processing"}`+"\n",
		rand.Int31n(0xffffff),
	)
}

// buildArchiveXML собирает безвредный архив SocialVault для GET-пути. Значения
// экранируются, поэтому штатный путь сам по себе не является уязвимостью.
func buildArchiveXML(params map[string]string) string {
	return fmt.Sprintf(`<?xml version="1.0"?>
<socialArchive exportedAt="2026-05-18T09:30:00Z">
  <profile id="acct-7142">
    <handle>%s</handle>
    <displayName>%s</displayName>
    <network>%s</network>
    <risk>%s</risk>
  </profile>
  <posts>
    <post id="p-9182">
      <text>Maintenance window completed. Access restored.</text>
      <likes>18</likes>
      <shares>4</shares>
    </post>
  </posts>
</socialArchive>
`,
		xmlEscape(params["handle"]),
		xmlEscape(params["displayName"]),
		xmlEscape(params["network"]),
		xmlEscape(params["risk"]),
	)
}

// xmlEscape безопасно экранирует значения, которые вставляются в штатный XML
// для обычного GET-запроса.
func xmlEscape(value string) string {
	var builder strings.Builder
	if err := xml.EscapeText(&builder, []byte(value)); err != nil {
		return value
	}
	return builder.String()
}

// processArchive имитирует фонового воркера импорта. Сначала запускается
// намеренно небезопасный legacy-слой совместимости с entity, затем архив
// парсится как обычный XML для логирования.
func processArchive(document string) {
	if err := processLegacyEntities(document); err != nil {
		log.Printf("legacy parser warning: %v", err)
	}

	var archive socialArchive
	if err := xml.Unmarshal([]byte(document), &archive); err != nil {
		log.Printf("archive parse failed: %v", err)
		return
	}

	log.Printf("archive queued: handle=%s display=%q",
		archive.Profile.Handle,
		archive.Profile.DisplayName,
	)
}

// processLegacyEntities несколько раз раскрывает небольшой поднабор DTD entity,
// нужный для задания. Это намеренно уязвимый слой, который включает blind
// XXE/OOB-поведение.
func processLegacyEntities(document string) error {
	entities := map[string]string{}
	work := document

	for range 8 {
		next, changed, err := processEntityPass(work, entities)
		if err != nil {
			return err
		}
		work = next
		if !changed {
			return nil
		}
	}

	return nil
}

// processEntityPass за один проход находит объявления entity, резолвит SYSTEM
// identifiers и раскрывает ссылки на parameter entities внутри документа.
func processEntityPass(input string, entities map[string]string) (string, bool, error) {
	changed := false

	for _, entity := range parseEntities(input) {
		if entity.SystemID != "" {
			resolved := expandParamRefs(entity.SystemID, entities)
			value, err := resolveSystemID(resolved)
			if err != nil {
				log.Printf("entity %s resolution failed: %v", entity.Name, err)
				continue
			}
			entities[entity.Name] = value
			changed = true
			continue
		}

		value := htmlPercentRE.ReplaceAllString(entity.Value, "%")
		value = expandParamRefs(value, entities)
		entities[entity.Name] = value
		changed = true
	}

	next := paramRefRE.ReplaceAllStringFunc(input, func(match string) string {
		name := strings.TrimSuffix(strings.TrimPrefix(match, "%"), ";")
		if value, ok := entities[name]; ok {
			changed = true
			return value
		}
		return match
	})

	return next, changed, nil
}

// parseEntities извлекает простые internal и SYSTEM entity declarations из DTD.
// Поддерживается только синтаксис, нужный для этой задачи.
func parseEntities(input string) []legacyEntity {
	var out []legacyEntity

	for _, match := range systemEntityRE.FindAllStringSubmatch(input, -1) {
		out = append(out, legacyEntity{
			Name:        match[2],
			IsParameter: match[1] == "%",
			SystemID:    match[3],
		})
	}

	for _, match := range valueEntityRE.FindAllStringSubmatch(input, -1) {
		out = append(out, legacyEntity{
			Name:        match[2],
			IsParameter: match[1] == "%",
			Value:       match[3],
		})
	}

	return out
}

// expandParamRefs заменяет ссылки на parameter entities их известными значениями.
// Значения URL-экранируются, чтобы содержимое файла можно было встроить в OOB
// callback URL.
func expandParamRefs(value string, entities map[string]string) string {
	return paramRefRE.ReplaceAllStringFunc(value, func(match string) string {
		name := strings.TrimSuffix(strings.TrimPrefix(match, "%"), ";")
		if entityValue, ok := entities[name]; ok {
			return url.QueryEscape(entityValue)
		}
		return match
	})
}

// resolveSystemID - опасный resolver. Он читает локальные file:// цели и делает
// исходящие HTTP(S)-запросы, за счет чего XXE становится blind/OOB.
func resolveSystemID(raw string) (string, error) {
	switch {
	case strings.HasPrefix(raw, "file://"):
		path := strings.TrimPrefix(raw, "file://")
		data, err := os.ReadFile(path)
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(string(data)), nil

	case strings.HasPrefix(raw, "http://") || strings.HasPrefix(raw, "https://"):
		client := http.Client{Timeout: 4 * time.Second}
		resp, err := client.Get(raw)
		if err != nil {
			return "", err
		}
		defer resp.Body.Close()

		body, err := io.ReadAll(io.LimitReader(resp.Body, 128*1024))
		if err != nil {
			return "", err
		}
		return string(body), nil

	default:
		return "", fmt.Errorf("unsupported SYSTEM identifier: %s", raw)
	}
}
