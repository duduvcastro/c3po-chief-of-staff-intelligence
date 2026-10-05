// Offline standard text/template proof. It does not contact Docker or the host.
package main

import (
    "bytes"
    "encoding/json"
    "flag"
    "fmt"
    "io"
    "os"
    "strings"
    "text/template"
)

type Config struct { Env []string }
type TypedInput struct { Config Config }
type Request struct { Template string `json:"template"`; Env []string `json:"env"` }

func fail(code string) { fmt.Fprintln(os.Stderr, code); os.Exit(1) }
func failError(code string, err error) { fmt.Fprintln(os.Stderr, code); fmt.Fprintln(os.Stderr, err); os.Exit(1) }
func main() {
    mode := flag.String("mode", "", "typed or raw")
    flag.Parse()
    if flag.NArg() != 0 || (*mode != "typed" && *mode != "raw") { fail("DRIVER_MODE_REFUSED") }
    raw, err := io.ReadAll(io.LimitReader(os.Stdin, 65537))
    if err != nil || len(raw) == 0 || len(raw) > 65536 { fail("DRIVER_INPUT_REFUSED") }
    var req Request
    dec := json.NewDecoder(bytes.NewReader(raw)); dec.DisallowUnknownFields()
    if dec.Decode(&req) != nil || dec.Decode(new(interface{})) != io.EOF || len(req.Template) == 0 || len(req.Env) > 128 { fail("DRIVER_JSON_REFUSED") }
    funcs := template.FuncMap{
        "split": strings.Split,
        "json": func(value interface{}) (string, error) { raw, err := json.Marshal(value); return string(raw), err },
    }
    tmpl, err := template.New("actual_environment_format").Option("missingkey=error").Funcs(funcs).Parse(req.Template)
    if err != nil { failError("LITERAL_TEMPLATE_PARSE_FAILED", err) }
    var data interface{}
    if *mode == "typed" {
        data = TypedInput{Config: Config{Env: req.Env}}
    } else {
        // The second execution uses interface-valued JSON arrays, as opposed to a typed []string.
        rawData, err := json.Marshal(map[string]interface{}{"Config": map[string]interface{}{"Env": req.Env}})
        if err != nil { fail("RAW_MODEL_FAILED") }
        decoder := json.NewDecoder(bytes.NewReader(rawData)); decoder.UseNumber()
        if decoder.Decode(&data) != nil { fail("RAW_MODEL_FAILED") }
    }
    var out bytes.Buffer
    if err := tmpl.Execute(&out, data); err != nil { failError("LITERAL_TEMPLATE_EXECUTION_FAILED", err) }
    if out.Len() > 16384 { fail("LITERAL_TEMPLATE_OUTPUT_TOO_LARGE") }
    if _, err := os.Stdout.Write(out.Bytes()); err != nil { fail("DRIVER_OUTPUT_FAILED") }
}
