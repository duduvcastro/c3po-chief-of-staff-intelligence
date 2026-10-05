"""Read-only combined preflight W1 for the epoch gates (reader launch, daily manifest, journal on the root filesystem).

Observations only: metadata, versions, counts and booleans. No shell, network, write, container command,
application import or systemd verb other than show. No environment value of any container enters this process:
one template makes the Docker CLI print fixed tokens for a fixed list of keys and literal lines, nothing else.
No entry name of any directory is stored, returned or emitted; directories are reduced to counts and histograms.
The file contents this process reads are listed in SCOPE file_contents_read; what the fixed tools do on their
own is listed in SCOPE side_effects. The caller authenticates exact request/authority/GO/source bytes first; every
step rechecks the signed UTC window and a monotonic deadline. A failed observation is reported unavailable with a
reason code and makes the receipt PARTIAL; it is never reported as absent. Something observed and unexpected is
a finding: findings are listed and do not change the status. No action on import.
"""
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import selectors
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone


class Refused(ValueError): pass
class CommandFailed(Refused):
    def __init__(self,code,returncode):
        Refused.__init__(self,code);self.returncode=returncode
def need(ok,code):
    if not ok:raise Refused(code)

OPERATION='GO_READONLY_W1PREFLIGHT_01'
PHASE='READONLY_W1PREFLIGHT'
# The whole signed window must lie on ONE of these UTC dates, never across midnight UTC (21:00 BRT is 00:00Z of the
# next date). The same bytes serve every read through Saturday 2026-10-10; each read is bound and signed on its own.
DATES=['2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10']
REQUEST_SCHEMA='READONLY_W1PREFLIGHT01_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_W1PREFLIGHT01_AUTHORITY_V1'
GO_SCHEMA='READONLY_W1PREFLIGHT01_GO_V1'
RECEIPT_SCHEMA='READONLY_W1PREFLIGHT01_RECEIPT_V1'
COLLECTION_SCHEMA='W1PREFLIGHT01_READONLY_REQUEST_V1'
OBSERVATION_SCHEMA='W1PREFLIGHT01_READONLY_OBSERVATION_V1'
COMPLETE_STATUS='METADATA_ONLY_REQUIRES_REVIEW'
PARTIAL_STATUS='PARTIAL_METADATA_REQUIRES_REVIEW'

MAX_SECONDS=60
CALL_SECONDS=5
# All docker commands together: a daemon that answers slowly without ever timing out may not use up the window.
DOCKER_SECONDS=25
# systemctl and pgrep together, by the same rule: slow answers of these two may not use up the window either.
SYSTEM_TOOLS_SECONDS=15
MAX_TOOL_TIMEOUTS=2
MAX_COMMAND_BYTES=64*1024
MAX_LISTED=64
MAX_FAMILY=16
MAX_MOUNTS=16
MAX_NETWORKS=8
MAX_DEPTH=16
MAX_IMAGES=4
MAX_WORKERS=4
MAX_FLAGS=64
MAX_PROBLEMS=64
MAX_FINDINGS=96
MAX_RELEASE_CANDIDATES=4
MAX_CAPACITY_CANDIDATES=3
CENSUS_CAP=20000
HISTOGRAM_ROWS=12
MAX_DATES=CENSUS_CAP          # a set of dates is never cut before the listing itself is
RAW_SESSION_SAMPLE=3
READER_FILE_LIMIT=4096
MOUNTINFO_LIMIT=1024*1024
POLICY_LIMIT=4096
REPORT_LIMIT=1024*1024
MODULE_LIMIT=512*1024
DEPLOY_VERSION_LIMIT=64
KERNEL_RELEASE_LIMIT=256
REPORT_COUNT_LIMIT=1000000
RECEIPT_LIMIT=60000
SEAL_OVERHEAD=100

PROJECT_LABEL='com.docker.compose.project'
SERVICE_LABEL='com.docker.compose.service'
ONEOFF_LABEL='com.docker.compose.oneoff'
REVISION_LABEL='org.opencontainers.image.revision'
PROJECT='c3po'
BACKEND=['api','investor-relations-worker','r2d2-shadow-candidate-worker','r2d2-worker','server-usage-worker','valuation-worker']
SERVICES=sorted(BACKEND+['db','web'])
WORKER='r2d2-worker'
DATABASE='db'
FIXED_CONTAINER_NAMES=['c3po-massive','c3po-reader']
COMPOSE_NETWORK='c3po_c3po_internal'
NETWORKS=['c3po_c3po_internal','c3po_db_loopback','chief-of-staff-digital_default']
NETWORK_MODES=NETWORKS+['bridge','default','host','none']
NETWORK_DRIVERS=['bridge','host','ipvlan','macvlan','null','overlay']
NETWORK_SCOPES=['global','local','swarm']
USERNS_MODES=['','host','private']
VOLUMES=['c3po_c3po_capacity_unprovisioned','c3po_c3po_day_d_data','c3po_c3po_one_pagers','c3po_c3po_postgres']
CAPACITY_PLACEHOLDER='c3po_c3po_capacity_unprovisioned'
VOLUME_ROOT='/var/lib/docker/volumes'
APP_DIR='/opt/chief-of-staff-digital'
SECURITY_DIR=APP_DIR+'/runtime/security'
MAINTENANCE_DIR=SECURITY_DIR+'/maintenance'
DATA_DESTINATION='/app/day-d-data'
CAPACITY_DESTINATION='/c3po-capacity'
DATA_SOURCES=['/mnt/day-d-data',VOLUME_ROOT+'/c3po_c3po_day_d_data/_data']
MOUNT_DESTINATIONS=[DATA_DESTINATION,CAPACITY_DESTINATION,'/app/generated-one-pagers','/host/disk','/host/proc/stat','/legacy',
                    '/run/c3po-maintenance','/var/lib/postgresql/data']
MOUNT_SOURCES=[APP_DIR,MAINTENANCE_DIR,'/proc/stat']+DATA_SOURCES+[VOLUME_ROOT+'/'+name+'/_data' for name in VOLUMES]
IMAGE_TAGS=['c3po/backend:production','c3po/backend:rollback','c3po/web:production','c3po/database:production']
MANDATORY_TAG='c3po/backend:production'
SERVICE_TAG={'db':'c3po/database:production','web':'c3po/web:production'}
# The supervisor's retention tag carries an operator-chosen label: tags of this shape are counted, never emitted.
RETENTION_TAG_PATTERN='c3po/backend:massive-supervisor-[a-z0-9][a-z0-9.-]{0,39}'
EPOCH='R2D2-V2-SHADOW-2026-10-05'
SESSIONS=['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09']
RAW_PARTS=['provider=eodhd','microstructure','raw']
SOURCE_CANDIDATES=['r2d2-v2-source']
PIN_NAME='.r2d2-v2-pinned'
JOURNAL_BASE='/var/lib'
JOURNAL_PARENT='/var/lib/c3po-bar'
JOURNAL_ROOT='/var/lib/c3po-bar/journal'
STATE_ROOT='/var/lib/c3po-bar/supervisor'
FLOOR_BYTES=53687091200
FIVE_SESSION_NEED_BYTES=56706990080
CAPACITY_CHILDREN=['config','documents','go','payload']
UNIT_DIRECTORY='/etc/systemd/system'
UNIT_FILES=['c3po-massive.service','c3po-massive.timer','c3po-reader.service','c3po-reader.timer','c3po-reader-alert.service']
# path, documented type, documented mode (root:root is documented for every one of them), immediate entries counted
LAYOUT=[['/etc/c3po-bar','dir','0700',True],['/etc/c3po-bar/manifests','dir','0700',True],['/etc/c3po-bar/docker-cli','dir','0700',True],
        ['/etc/c3po-bar/token','file','0600',False],['/etc/c3po-reader','dir','0700',True],['/etc/c3po-reader/docker-cli','dir','0700',True],
        ['/etc/c3po-reader/launcher','dir','0700',True],['/etc/c3po-reader/launcher/reader_launcher.py','file','0600',False],
        ['/etc/c3po-reader/secret.env','file','0600',False],['/etc/c3po-reader/pins.env','file','0600',False],
        ['/etc/c3po-reader/activation.env','file','0600',False],['/var/lib/c3po-reader','dir','0700',True],['/opt/c3po-bar',None,None,False],
        [UNIT_DIRECTORY,'dir','0755',False]]+[[UNIT_DIRECTORY+'/'+name,'file','0644',False] for name in UNIT_FILES]
TOKEN_PATH='/etc/c3po-bar/token'
MANIFESTS_PATH='/etc/c3po-bar/manifests'
DOCKER_UNIT='docker.service'
# The Docker CLI's own default endpoint, named in every argv so that no client context can send a read elsewhere.
DOCKER_ENDPOINT='unix:///var/run/docker.sock'
KERNEL_RELEASE='/proc/sys/kernel/osrelease'
UNITS=UNIT_FILES+['c3po-security-daily.timer','c3po-security-watchdog.timer','c3po-host-security-snapshot.timer','apt-daily-upgrade.timer',
                  'c3po-unattended-upgrades-healthcheck-failure.service']
LOAD_STATES=['bad-setting','error','loaded','masked','merged','not-found','stub']
ACTIVE_STATES=['activating','active','deactivating','failed','inactive','maintenance','refreshing','reloading']
FILE_STATES=['','alias','bad','disabled','enabled','enabled-runtime','generated','indirect','linked','linked-runtime','masked',
             'masked-runtime','static','transient']
SUB_STATES=['abandoned','auto-restart','dead','elapsed','exited','failed','running','start','start-pre','stop','waiting']
REBOOT_REQUIRED='/run/reboot-required'
SECURITY_PROBES={'reboot_required':REBOOT_REQUIRED,'reboot_required_packages':'/run/reboot-required.pkgs',
                 'reboot_flag_writer':'/usr/share/update-notifier/notify-reboot-required',
                 'controller_reboot_marker':'/run/c3po-security/reboot.pending','gate_reboot_marker':MAINTENANCE_DIR+'/reboot.pending',
                 'maintenance_hold':'/etc/c3po/security-maintenance.hold','host_security_environment':'/etc/c3po/host-security.env',
                 'reboot_state':SECURITY_DIR+'/security-reboot-state.json'}
VAR_RUN='/var/run'
POLICY_DIR='/etc/c3po'
POLICY_NAME='security-automation.json'
POLICY_SCHEMA='C3PO_SECURITY_AUTOMATION_POLICY-v1'
AUTOMATION_REPORT='security-automation-report.json'
HOST_REPORT='host-os-vulnerability-report.json'
HOST_REPORT_SCHEMA='C3PO_HOST_OS_VULNERABILITY_REPORT-v1'
MODULE_DIR='/usr/local/lib/c3po-security'
MODULES=['c3po_security_daily.py','c3po_security_guard.py','c3po_security_reboot.py']
REBOOT_ACTIONS=['cooldown','deferred','not_needed_or_disabled','requested','waiting_active_jobs','waiting_admission',
                'waiting_admission_coverage','waiting_database_work','waiting_ingestion_work','waiting_packages',
                'waiting_packages_or_deploy','waiting_pipeline','waiting_scheduled_jobs']
AUTOMATION_STATUS=['baseline_changed_or_hold','blocked_branch_protection','blocked_missing_evidence','blocked_scan_dispatch',
                   'blocked_unhealthy_host','failed','maintenance_hold','merged_waiting_deploy_and_rescan','no_validated_candidate',
                   'observed','reboot_requested','waiting_branch_rules','waiting_main_deploy','waiting_maintenance_window',
                   'waiting_pipeline','waiting_security_tests']+['reboot_'+action for action in REBOOT_ACTIONS]
ALERT_PROBES={'healthcheck_ping':'/usr/local/sbin/c3po-healthcheck-ping',
              'healthcheck_dropin':'/etc/systemd/system/apt-daily-upgrade.service.d/c3po-healthcheck.conf',
              'reader_failure_marker_directory':'/var/lib/c3po-reader','sendmail':'/usr/sbin/sendmail','mail':'/usr/bin/mail',
              'mailx':'/usr/bin/mailx','msmtp':'/usr/bin/msmtp','postfix':'/usr/sbin/postfix','exim4':'/usr/sbin/exim4',
              'ssmtp':'/usr/sbin/ssmtp','curl':'/usr/bin/curl'}
PROCESS_PATTERNS=[['shadow_worker','r2d2_v2_shadow_worker'],['reader_launcher','reader_launcher\\.py'],
                  ['massive_supervisor','r2d2_v2_massive_supervisor'],['manifest_writer','manifest_writer\\.py']]
FILESYSTEM_TYPES=['btrfs','ext2','ext3','ext4','f2fs','nfs','nfs4','overlay','tmpfs','vfat','xfs','zfs']
DEVICE_PATTERN='/dev/(nvme[0-9]{1,3}n[0-9]{1,3}(p[0-9]{1,3})?|(xvd|sd|vd|hd)[a-z]{1,3}[0-9]{0,3}|loop[0-9]{1,3}|md[0-9]{1,3}|dm-[0-9]{1,3}|root)'
ENTRY='[A-Za-z0-9._=-]{1,64}'
HISTOGRAM_COLUMNS=['type','uid','gid','mode_octal','count']
# Counted over the immediate entries that are not symbolic links; a counter that is zero is not listed.
COUNTERS=['not_uid0','private_not_uid0','not_private','group_other_writable','uid0_nocap_unreadable','symlink']
DAY='[0-9]{4}-[0-9]{2}-[0-9]{2}'
NAME_CLASSES={'trial_or_probe':'\\.r2d2-v2-(?:trial|probe)-(\\d{8})(?:-r\\d+)?','session_directory':'session_date=('+DAY+')',
              'raw_part':'feed=(quote|trade)-part-\\d{5,}\\.ndjson','day_file':'('+DAY+')\\.json',
              'diagnostic_release':'r2d2-v2-release-diagnostic-[0-9a-f]{8,64}\\.json'}
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl'],
          'pgrep':['/usr/bin/pgrep','/bin/pgrep']}
MOUNT_BASIS=('"/" is reported true by definition; any other component is a mount point when its st_dev differs '
             'from its parent; the holder is the last /proc mountinfo entry whose mount point is the longest prefix of the path')

# Docker templates. PS, CLASS, FAMILY, IMAGE and VERSION are the bytes proven on this host by the earlier read of
# 2026-10-02. Every container template names .Id, so it runs in the CLI raw-JSON fallback (missingkey=error), the
# only inspect mode proven on this host; each optional key is reached through index and never by a dotted reference.
def _label(key):
    return '{{with index .Config "Labels"}}{{json (index . "'+key+'")}}{{else}}null{{end}}'
PS_FORMAT='{"id":{{json .ID}},"name":{{json .Names}},"state":{{json .State}}}'
CLASS_FORMAT=('{"id":{{json .Id}},"running":{{json .State.Running}},"project":'+_label(PROJECT_LABEL)
              +',"service":'+_label(SERVICE_LABEL)+',"oneoff":'+_label(ONEOFF_LABEL)+'}')
FAMILY_FORMAT=('{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},'
               '"image_reference":{{json .Config.Image}},"running":{{json .State.Running}},'
               '"state":{{json .State.Status}},"started_at":{{json .State.StartedAt}},'
               '"host_pid":{{json .State.Pid}},"restarts":{{json .RestartCount}},'
               '"project":'+_label(PROJECT_LABEL)+',"service":'+_label(SERVICE_LABEL)
               +',"oneoff":'+_label(ONEOFF_LABEL)+',"revision":'+_label(REVISION_LABEL)
               +',"user":{{json (index .Config "User")}},"userns_mode":{{json (index .HostConfig "UsernsMode")}},'
               '"readonly_rootfs":{{json (index .HostConfig "ReadonlyRootfs")}},'
               '"network_mode":{{json (index .HostConfig "NetworkMode")}},'
               '"networks":[{{range $k, $v := index .NetworkSettings "Networks"}}{{json $k}},{{end}}null],'
               '"mounts":[{{range $m := index . "Mounts"}}{"type":{{json (index $m "Type")}},'
               '"source":{{json (index $m "Source")}},"destination":{{json (index $m "Destination")}},'
               '"rw":{{json (index $m "RW")}}},{{end}}null]}')
IMAGE_FORMAT=('{"id":{{json .Id}},"repo_tags":{{json (index . "RepoTags")}},"revision":'
              '{{with index . "Config"}}{{with index . "Labels"}}{{json (index . "'+REVISION_LABEL+'")}}'
              '{{else}}null{{end}}{{else}}null{{end}}}')
VERSION_FORMAT='{{json .Server.Version}}'
# NEW, never run on any engine. The environment list is ranged over inside the Docker CLI; the only things the
# template can print are the container id and the fixed tokens below. No value and no key leaves the CLI process.
ENV_KEYS=[['C3PO_DATABASE_URL','DATABASE_URL_KEY'],['C3PO_R2D2_V2_CAPACITY_REQUIRED','CAPACITY_REQUIRED_KEY'],
          ['C3PO_R2D2_V2_CAPACITY_CONFIG_FILE','CAPACITY_CONFIG_FILE_KEY'],['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','CAPACITY_CONFIG_SHA_KEY'],
          ['C3PO_R2D2_V2_CAPACITY_VETO_MODE','CAPACITY_VETO_MODE_KEY'],['C3PO_R2D2_V2_SHADOW_ENABLED','SHADOW_ENABLED_KEY'],
          ['C3PO_R2D2_V2_MASSIVE_BARS_ENABLED','MASSIVE_BARS_ENABLED_KEY'],['C3PO_R2D2_V2_SHADOW_RELEASE_FILE','SHADOW_RELEASE_FILE_KEY'],
          ['C3PO_R2D2_V2_SHADOW_RELEASE_SHA','SHADOW_RELEASE_SHA_KEY'],['C3PO_R2D2_V2_SHADOW_SOURCE_DIR','SHADOW_SOURCE_DIR_KEY'],
          ['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR','MASSIVE_JOURNAL_DIR_KEY'],['C3PO_R2D2_V2_LIVE_POLICY_FILE','LIVE_POLICY_FILE_KEY'],
          ['C3PO_R2D2_V2_LIVE_POLICY_SHA','LIVE_POLICY_SHA_KEY'],['C3PO_R2D2_MICROSTRUCTURE_RAW_DIR','RAW_DIR_KEY']]
ENV_LINES=[['C3PO_DATABASE_URL=','DATABASE_URL_EMPTY'],['C3PO_R2D2_V2_CAPACITY_REQUIRED=true','CAPACITY_REQUIRED_TRUE'],
           ['C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY','CAPACITY_VETO_MODE_DOCUMENTED'],
           ['C3PO_R2D2_V2_SHADOW_ENABLED=true','SHADOW_ENABLED_TRUE'],['C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true','MASSIVE_BARS_ENABLED_TRUE'],
           ['C3PO_R2D2_V2_SHADOW_SOURCE_DIR='+DATA_DESTINATION+'/'+SOURCE_CANDIDATES[0],'SHADOW_SOURCE_DIR_IS_CANDIDATE'],
           ['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=','MASSIVE_JOURNAL_DIR_EMPTY'],
           ['C3PO_R2D2_MICROSTRUCTURE_RAW_DIR='+DATA_DESTINATION+'/'+'/'.join(RAW_PARTS),'RAW_DIR_DOCUMENTED']]
ENV_TOKENS=[token for _,token in ENV_KEYS+ENV_LINES]
ENVFLAGS_FORMAT=('{"id":{{json .Id}},"flags":[{{range $e := index .Config "Env"}}{{$k := index (split $e "=") 0}}'
                 +''.join('{{if eq $k "'+key+'"}}"'+token+'",{{end}}' for key,token in ENV_KEYS)
                 +''.join('{{if eq $e "'+line+'"}}"'+token+'",{{end}}' for line,token in ENV_LINES)+'{{end}}null]}')
# NEW, never run on any engine: the proven container mode, the proven range over Networks, one more index.
ATTACH_FORMAT=('{"id":{{json .Id}},"networks":[{{range $k, $v := index .NetworkSettings "Networks"}}{"name":{{json $k}},'
               '"network_id":{{json (index $v "NetworkID")}}},{{end}}null]}')
# NEW, never run on any engine. It names no id on purpose: every key below is a field of the CLI's typed structure
# and a key of the raw JSON under the same spelling, so the template executes in either inspect mode.
NETWORK_FORMAT=('{"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},"internal":{{json .Internal}},'
                '"attachable":{{json .Attachable}},"containers":[{{range $k, $v := .Containers}}{{json $k}},{{end}}null]}')
TEMPLATES={'PS_FORMAT':PS_FORMAT,'CLASS_FORMAT':CLASS_FORMAT,'FAMILY_FORMAT':FAMILY_FORMAT,'IMAGE_FORMAT':IMAGE_FORMAT,
           'VERSION_FORMAT':VERSION_FORMAT,'ENVFLAGS_FORMAT':ENVFLAGS_FORMAT,'ATTACH_FORMAT':ATTACH_FORMAT,'NETWORK_FORMAT':NETWORK_FORMAT}
PROVEN_TEMPLATES=['CLASS_FORMAT','FAMILY_FORMAT','IMAGE_FORMAT','PS_FORMAT','VERSION_FORMAT']

ENDPOINT_ARGV=['--host',DOCKER_ENDPOINT]
# The exact fixed argv prefixes. The signed request carries this table, so the commands this process starts are
# the signed bytes by construction. What those tools start or read on their own is not argv of this process.
COMMANDS={'ps':['docker',ENDPOINT_ARGV+['ps','-a','--no-trunc','--format',PS_FORMAT],None],
          'class':['docker',ENDPOINT_ARGV+['container','inspect','--format',CLASS_FORMAT],'64-hex container id from ps'],
          'family':['docker',ENDPOINT_ARGV+['container','inspect','--format',FAMILY_FORMAT],'64-hex container id from ps'],
          'envflags':['docker',ENDPOINT_ARGV+['container','inspect','--format',ENVFLAGS_FORMAT],'64-hex id of a running r2d2-worker container'],
          'attach':['docker',ENDPOINT_ARGV+['container','inspect','--format',ATTACH_FORMAT],'64-hex id of the running db or r2d2-worker container'],
          'network':['docker',ENDPOINT_ARGV+['network','inspect','--format',NETWORK_FORMAT,COMPOSE_NETWORK],None],
          'image':['docker',ENDPOINT_ARGV+['image','inspect','--format',IMAGE_FORMAT],'a tag of image_tags, or the sha256 image id of a stack container'],
          'version':['docker',ENDPOINT_ARGV+['version','--format',VERSION_FORMAT],None],
          'docker_unit':['systemctl',['show',DOCKER_UNIT,'-p','Id','-p','ActiveState','-p','SubState','-p','UnitFileState'],None]}
COMMANDS.update({'unit:'+unit:['systemctl',['show',unit,'-p','Id','-p','LoadState','-p','ActiveState','-p','UnitFileState'],None]
                 for unit in UNITS})
COMMANDS.update({'process:'+label:['pgrep',['-c','-f',pattern],None] for label,pattern in PROCESS_PATTERNS})

FILE_CONTENTS_READ=['/proc/<pid of this process>/mountinfo',KERNEL_RELEASE,APP_DIR+'/.deploy-version',POLICY_DIR+'/'+POLICY_NAME,
                    SECURITY_DIR+'/'+AUTOMATION_REPORT,SECURITY_DIR+'/'+HOST_REPORT]+[MODULE_DIR+'/'+name for name in MODULES]
SIDE_EFFECTS=['no docker command is started unless systemctl show answered ActiveState=active for '+DOCKER_UNIT+' in this run: a client '
              'call to the endpoint of a stopped daemon can make the service manager start it, and a started daemon restarts '
              'containers. Not covered: a daemon that stops between that answer and a later docker command',
              'every docker command names the endpoint '+DOCKER_ENDPOINT+' in its argv; the Docker CLI still loads its client '
              'configuration file from the home directory of root when one exists; its content never reaches this process',
              'every container, image and network inspect: the Docker CLI process receives the whole inspect document from the '
              'daemon, environment and addresses included, in order to render the template; this process receives the template '
              'output only',
              'systemctl show of a unit that is not loaded makes the manager look for its unit file; nothing is started',
              'pgrep reads the command line of every process; this process receives one number',
              'signals: a child that exceeds its time limit is sent SIGKILL by this process; no other signal is sent',
              'each child gets the null device as stdin and stderr, which the Python library opens read-write; nothing is '
              'written to it',
              'access times: every open of this process outside /proc carries O_NOATIME; readlink of /var/run and the file '
              'reads of the three tools themselves may move access times under the mount options of the host',
              'automounts: nothing is opened at or below a mount point whose last mount table row is autofs, nor is a tree '
              'descended that has such a point below it (AUTOMOUNT_PATH_REFUSED); the mount table itself is read from /proc '
              'before that check exists, and without a mount table the check is not applied (automount_guard says so)',
              'docker info, timedatectl and getent are not run: their facts were measured by the earlier read and do not change '
              'with a deploy']
SCOPE={'operation':OPERATION,'dates':DATES,
       'binaries':BINARIES,'commands':COMMANDS,'docker_endpoint':DOCKER_ENDPOINT,
       'docker_precondition':DOCKER_UNIT+' ActiveState=active observed by systemctl show in this run, before the first docker command',
       'command_environment':{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},
       'stack':{'project_label':PROJECT_LABEL,'project':PROJECT,'service_label':SERVICE_LABEL,'services':SERVICES,'backend':BACKEND,
                'oneoff_label':ONEOFF_LABEL,'revision_label':REVISION_LABEL,'fixed_container_names':FIXED_CONTAINER_NAMES,
                'image_tags':IMAGE_TAGS,'retention_tag_pattern_counted_never_emitted':RETENTION_TAG_PATTERN},
       'allow_lists':{'networks':NETWORKS,'volumes':VOLUMES,'mount_destinations':MOUNT_DESTINATIONS,'mount_sources':MOUNT_SOURCES,
                      'data_sources':DATA_SOURCES,'filesystem_types':FILESYSTEM_TYPES,'device_pattern':DEVICE_PATTERN,
                      'environment_tokens':ENV_TOKENS},
       'environment_flags':{'keys':ENV_KEYS,'literal_lines':ENV_LINES,
                            'output':'fixed tokens only; computed inside the Docker CLI; no value and no key reaches this process'},
       'data_destination':DATA_DESTINATION,'capacity_destination':CAPACITY_DESTINATION,
       'epoch':EPOCH,'sessions':SESSIONS,
       'journal':{'base':JOURNAL_BASE,'parent':JOURNAL_PARENT,'root':JOURNAL_ROOT,'state_root':STATE_ROOT,
                  'floor_bytes':FLOOR_BYTES,'five_session_need_bytes':FIVE_SESSION_NEED_BYTES,
                  'figure':'f_bavail*f_frsize of the deepest existing directory among base, parent and root'},
       'aggregates_only':{'rule':'immediate entries reduced to counts, type/uid/gid/mode histograms and fixed name classes; no entry '
                                 'name is stored or emitted; dates of the classes with a date are the only text taken from a name',
                          'data_source_root':{'pin':PIN_NAME,'name_classes':NAME_CLASSES},
                          'raw_spool':{'below_data_source':RAW_PARTS,'sampled_newest_sessions':RAW_SESSION_SAMPLE},
                          'source_directories':{'below_data_source':SOURCE_CANDIDATES,
                                                'children':['snapshot.json','events','causal_list','causal_list/'+EPOCH]},
                          'release_directories':'request.collection.candidates.release_directories, single names below the data source',
                          'capacity_roots':{'paths':'request.collection.candidates.capacity_roots','children':CAPACITY_CHILDREN},
                          'journal_root':JOURNAL_ROOT,'layout_directories':[row[0] for row in LAYOUT if row[3]],
                          'entry_cap':CENSUS_CAP,'histogram_columns':HISTOGRAM_COLUMNS,
                          'counters':{'names':COUNTERS,'rule':'a counter that is zero is not listed; symlink counts the links, the '
                                      'others count the entries that are not links; private means no group or other permission bit; '
                                      'uid0_nocap_unreadable means uid 0 and gid 0 without any capability cannot read it, or cannot '
                                      'search it when it is a directory'}},
       'lstat_only':{'layout':LAYOUT,'security':SECURITY_PROBES,'var_run':VAR_RUN,'alert_channels':ALERT_PROBES,
                     'token':'type, uid, gid, mode, link count and whether the size is within 1-4096; never the size, never the content'},
       'readlink':[VAR_RUN],
       'statvfs':['data source','deepest existing directory among '+JOURNAL_BASE+', '+JOURNAL_PARENT+' and '+JOURNAL_ROOT],
       'file_contents_read':FILE_CONTENTS_READ,
       'in_process':['sys.version_info','sys.implementation.name','CLOCK_BOOTTIME','wall clock'],
       'versions':'of the kernel release and of the Docker server version only the leading dotted number is emitted (and the '
                  'number that follows it in a kernel release); any other suffix is reported as withheld',
       'processes':{'patterns':PROCESS_PATTERNS,'output':'one count per pattern; no command line reaches this process'},
       'side_effects':SIDE_EFFECTS,
       'never':['container environment value or key','docker exec or run','any write','provider token content, size or digest',
                'database content or connection','instrument symbols','entry names of any directory',
                'file contents other than file_contents_read','content of the reader secret file, the pins file, the hold file, '
                'the package list, the host security environment file, the reboot state file or any release file',
                'systemctl verbs other than show','shell','network connection opened by this process','host name','os.uname',
                'docker command while '+DOCKER_UNIT+' was not observed active','docker endpoint other than '+DOCKER_ENDPOINT,
                'address of any network','docker info','timedatectl','getent'],
       'limits':{'max_seconds':MAX_SECONDS,'call_seconds':CALL_SECONDS,'docker_seconds':DOCKER_SECONDS,
                 'system_tools_seconds':SYSTEM_TOOLS_SECONDS,
                 'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,'report_count':REPORT_COUNT_LIMIT,
                 'command_output_bytes':MAX_COMMAND_BYTES,'listed_containers':MAX_LISTED,'stack_rows':MAX_FAMILY,
                 'mounts_per_container':MAX_MOUNTS,'networks_per_container':MAX_NETWORKS,'images_by_id':MAX_IMAGES,
                 'workers':MAX_WORKERS,'path_depth':MAX_DEPTH,'histogram_rows':HISTOGRAM_ROWS,'reader_file_limit':READER_FILE_LIMIT,
                 'release_candidates':MAX_RELEASE_CANDIDATES,'capacity_candidates':MAX_CAPACITY_CANDIDATES,
                 'mountinfo_bytes':MOUNTINFO_LIMIT,'kernel_release_bytes':KERNEL_RELEASE_LIMIT,'policy_bytes':POLICY_LIMIT,'report_bytes':REPORT_LIMIT,'module_bytes':MODULE_LIMIT,
                 'receipt_bytes':RECEIPT_LIMIT}}

HEX64='[0-9a-f]{64}'
HEX40='[0-9a-f]{40}'
NAME='[A-Za-z0-9][A-Za-z0-9_.-]{0,127}'
IMAGE_ID='sha256:[0-9a-f]{64}'
REFERENCE='[A-Za-z0-9_./:@-]{1,200}'
STAMP='[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,9})?(Z|[+-][0-9]{2}:[0-9]{2})'          # RFC 3339
CODE='[A-Z][A-Z0-9_]{0,79}'
STATES=('created','running','paused','restarting','removing','exited','dead')
MOUNT_TYPES=('bind','volume','tmpfs','npipe','cluster','image')
EXPIRED=('GO_EXPIRED','CLOCK_REVERSED','DEADLINE')
DIRECTORY=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(raw,limit=65536):
    need(type(raw) is bytes and 0<len(raw)<=limit,'DOCUMENT_SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'DUPLICATE_KEY');result[key]=value
        return result
    def constant(_):raise Refused('NONFINITE_JSON')
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except Refused:raise
    except (ValueError,RecursionError):raise Refused('JSON_INVALID')
def decode(raw,limit=65536):
    value=strict(raw,limit);need(type(value) is dict,'DOCUMENT_TYPE');return value
def instant(value):
    need(type(value) is str,'WINDOW_UNBOUND')
    point=datetime.fromisoformat(value.replace('Z','+00:00'));offset=point.utcoffset()
    need(point.tzinfo is not None and offset is not None and offset.total_seconds()==0,'WINDOW_NOT_UTC')
    return point
SCOPE_SHA256=sha(canonical(SCOPE))

def text(value,pattern):return type(value) is str and re.fullmatch(pattern,value) is not None
def clean_path(value):
    return (text(value,r'/[A-Za-z0-9._=/_-]{0,199}') and '//' not in value and str(PurePosixPath(value))==value
            and '..' not in PurePosixPath(value).parts and len(PurePosixPath(value).parts)<=MAX_DEPTH+1)
def data_path(value):
    return clean_path(value) and value!='/' and not any(value==root or value.startswith(root+'/') for root in ('/proc','/sys','/dev'))
def below(path,root):return path==root or path.startswith(root.rstrip('/')+'/')
def kind(mode):
    if stat.S_ISDIR(mode):return 'dir'
    if stat.S_ISREG(mode):return 'file'
    if stat.S_ISLNK(mode):return 'symlink'
    return 'other'
def leaf(info):
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode)}
def shape(info):
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,
            'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'device':info.st_dev,'inode':info.st_ino}
def seconds(info):return int(info.st_mtime_ns//1000000000)
def root_private(info,form):
    """root:root, the documented type, no group or other permission bit."""
    return kind(info.st_mode)==form and info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)&0o077==0
def access(info):
    """What uid 0 / gid 0 without any capability (--cap-drop ALL) may do: the owner bits of what uid 0 owns,
    otherwise the group bits when the group is 0, otherwise the other bits."""
    bits=(stat.S_IMODE(info.st_mode)>>(6 if info.st_uid==0 else 3 if info.st_gid==0 else 0))&7
    return {'read':bool(bits&4),'search_or_execute':bool(bits&1)}
def linux_device(number):
    """gnu_dev_major and gnu_dev_minor, computed here so that the result never depends on where a test runs."""
    return ((number>>8)&0xfff)|((number>>32)&~0xfff),(number&0xff)|((number>>12)&~0xff)
def token(value,allowed):return value if type(value) is str and value in allowed else None if value is None else 'OTHER'
def dotted(value):
    """(leading dotted number of two or three parts, the text after it) of a version text, or None. Only the number is
    ever emitted: four parts would have the shape of an address, and a suffix may carry any name."""
    match=re.fullmatch(r'([0-9]{1,3}(?:\.[0-9]{1,4}){1,2})((?:[-+~][ -~]{0,96})?)',value) if type(value) is str else None
    return (match.group(1),match.group(2)) if match else None
def tri(value):return 'true' if value is True else 'false' if value is False else 'absent' if value is None else 'other'
def safe(error):
    if isinstance(error,Refused) and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',str(error)):
        result={'status':'UNAVAILABLE','code':str(error)}
        if isinstance(error,CommandFailed) and type(error.returncode) is int:result['returncode']=error.returncode
        return result
    if isinstance(error,OSError):
        return {'status':'UNAVAILABLE','code':'OS_ERROR','errno':error.errno if type(error.errno) is int else None}
    return {'status':'UNAVAILABLE','code':'OBSERVATION_FAILED'}
def attempt(action):
    try:return action()
    except Exception as error:return safe(error)
def combined(items):
    statuses=[item.get('status') for item in items]
    if statuses and all(value=='COMPLETE' for value in statuses):return 'COMPLETE'
    return 'UNAVAILABLE' if statuses and all(value=='UNAVAILABLE' for value in statuses) else 'PARTIAL'
def finish(out,items=(),issues=(),findings=()):
    """Section status from its parts: COMPLETE only when every part is COMPLETE and no issue was raised."""
    parts=[item for item in items if type(item) is dict and 'status' in item]
    status=combined(parts) if parts else 'COMPLETE'
    if issues and status=='COMPLETE':status='PARTIAL'
    out['status']=status;out['issues']=sorted(set(issues));out['findings']=sorted(set(findings));return out


class Native:
    """The only place that touches the host: fixed-argv commands, metadata calls and bounded reads."""
    def identity(self):return os.geteuid(),os.getegid()
    def pid(self):return os.getpid()
    def now(self):return time.time()
    def python(self):return tuple(sys.version_info[:3]),sys.implementation.name
    def uptime(self):
        clock=getattr(time,'CLOCK_BOOTTIME',None);need(clock is not None,'BOOTTIME_UNAVAILABLE');return time.clock_gettime(clock)
    def noatime(self):
        flag=getattr(os,'O_NOATIME',0);need(flag,'NOATIME_UNAVAILABLE');return flag
    def open(self,name,flags,dir_fd=None):
        return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)
    def close(self,fd):os.close(fd)
    def fstat(self,fd):return os.fstat(fd)
    def lstat(self,name,dir_fd):return os.stat(name,dir_fd=dir_fd,follow_symlinks=False)
    def readlink(self,name,dir_fd):return os.readlink(name,dir_fd=dir_fd)
    def fstatvfs(self,fd):return os.fstatvfs(fd)
    def read(self,fd,size):return os.read(fd,size)
    def names(self,fd):
        with os.scandir(fd) as iterator:
            for entry in iterator:yield entry.name
    def run(self,argv,gate,seconds,capture=True):
        gate()
        process=subprocess.Popen(argv,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,
                                 env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
        output=bytearray();selector=selectors.DefaultSelector()
        try:
            until=time.monotonic()+min(seconds,gate())
            if capture:
                os.set_blocking(process.stdout.fileno(),False);selector.register(process.stdout,selectors.EVENT_READ)
                while selector.get_map():
                    remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                    for key,_ in selector.select(min(.2,remaining)):
                        block=os.read(key.fd,8192)
                        if not block:selector.unregister(key.fileobj);continue
                        output.extend(block);need(len(output)<=MAX_COMMAND_BYTES,'COMMAND_OUTPUT_LIMIT')
            while True:
                remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                try:code=process.wait(timeout=min(.2,remaining));break
                except subprocess.TimeoutExpired:pass
            gate();return code,bytes(output)
        finally:
            if process.poll() is None:
                process.kill()
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            selector.close()
            if process.stdout is not None:process.stdout.close()


def trusted_executable(host,path,check):
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    fd=host.open('/',flags)
    try:
        info=host.fstat(fd);parts=PurePosixPath(path).parts[1:]
        for index,part in enumerate(parts):
            if not (stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022):return False
            check()
            try:named=host.lstat(part,fd)
            except FileNotFoundError:return False
            if index==len(parts)-1:
                return bool(stat.S_ISREG(named.st_mode) and named.st_uid==0 and not named.st_mode&0o022 and named.st_mode&0o111)
            if not stat.S_ISDIR(named.st_mode):return False
            child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child;info=host.fstat(fd)
        return False
    finally:host.close(fd)

def binary(host,candidates,check):
    for candidate in candidates:
        if trusted_executable(host,candidate,check):return candidate
    raise Refused('BINARY_UNAVAILABLE_OR_UNSAFE')


class Context:
    # Closed until systemd() has seen the docker unit active; collect() sets the armed automount points.
    docker_block='DOCKER_SKIPPED_UNIT_UNOBSERVED';docker_floor=None;autofs=()
    system_floor=None
    def __init__(self,host,gate):
        self.host,self.gate,self.started=host,gate,time.monotonic()
        self.binaries={};self.timeouts={};self.calls=0
    def check(self):
        remaining=self.gate()
        need(time.monotonic()-self.started<MAX_SECONDS,'DEADLINE')
        return remaining
    def call(self,name,*extra,capture=True):
        tool,arguments,_=COMMANDS[name]
        # Nothing reaches the docker endpoint, not even the lookup of the binary, before the unit was seen active.
        if tool=='docker':need(self.docker_block is None,self.docker_block)
        need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')
        if tool not in self.binaries:
            try:
                for candidate in BINARIES[tool]:guarded(self,candidate)
                self.binaries[tool]=binary(self.host,BINARIES[tool],self.check)
            except Exception as error:self.binaries[tool]=Refused(safe(error)['code'])
        path=self.binaries[tool]
        if isinstance(path,Exception):raise Refused(str(path))
        # The one optional argument is a container id, an image id or a signed tag: never a free string, never an option.
        need(len(extra)<=1 and all(text(value,HEX64) or text(value,IMAGE_ID) or value in IMAGE_TAGS for value in extra),'ARGUMENT_INVALID')
        if tool=='docker':
            left=self.check()
            if self.docker_floor is None:self.docker_floor=left-DOCKER_SECONDS
            need(left>self.docker_floor,'DOCKER_BUDGET_EXHAUSTED')
        else:
            left=self.check()
            if self.system_floor is None:self.system_floor=left-SYSTEM_TOOLS_SECONDS
            need(left>self.system_floor,'SYSTEM_TOOLS_BUDGET_EXHAUSTED')
        self.calls+=1
        try:return self.host.run([path]+list(arguments)+list(extra),self.check,CALL_SECONDS,capture)
        except Refused as error:
            if str(error)=='COMMAND_TIMEOUT':self.timeouts[tool]=self.timeouts.get(tool,0)+1
            raise
    def output(self,name,*extra,failure='COMMAND_FAILED'):
        code,raw=self.call(name,*extra)
        if code!=0:raise CommandFailed(failure,code)
        return raw
    def path(self,tool):
        return self.binaries.get(tool) if type(self.binaries.get(tool)) is str else None

class Held:
    """Closes every descriptor kept in it, whatever happens."""
    def __init__(self,host):self.host,self.fds=host,[]
    def keep(self,fd):
        if fd is not None:self.fds.append(fd)
        return fd
    def __enter__(self):return self
    def __exit__(self,*failure):
        while self.fds:
            fd=self.fds.pop()
            try:self.host.close(fd)
            except Exception:pass
        return False


def guarded(ctx,path,tree=False):
    """Refuses a path that an armed automount point holds, and a tree that has such a point below it: an open with
    O_DIRECTORY would make the kernel mount it. The points come from the mount table read at the start."""
    for point in ctx.autofs:
        need(not below(path,point) and not (tree and below(point,path)),'AUTOMOUNT_PATH_REFUSED')

def locate(host,path,check):
    """lstat of the leaf only; no component is followed. Returns ('absent',prefix), ('symlink',prefix) or ('present',stat)."""
    flags=DIRECTORY|host.noatime()
    check();fd=host.open('/',flags)
    try:
        parts=PurePosixPath(path).parts[1:];prefix=''
        for index,part in enumerate(parts):
            prefix+='/'+part;check()
            try:named=host.lstat(part,fd)
            except FileNotFoundError:return 'absent',prefix
            if index==len(parts)-1:return 'present',named
            if stat.S_ISLNK(named.st_mode):return 'symlink',prefix
            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')
        return 'present',host.fstat(fd)
    finally:host.close(fd)

def probe(ctx,path,describe=shape):
    """Absence is proved at the first missing component, which absent_at names (every earlier component was opened without
    following a link). A link in the middle of the path is unavailable, never absent."""
    guarded(ctx,path);state,value=locate(ctx.host,path,ctx.check)
    if state=='absent':return {'status':'COMPLETE','exists':False,'absent_at':value}
    if state=='symlink':return {'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','at':value}
    return {'status':'COMPLETE','exists':True,**describe(value)}

def descend(host,path,check,rows):
    """Open a directory component by component, never following a link. One row per component, '/' included."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    check();fd=host.open('/',flags)
    try:
        info=host.fstat(fd);rows.append({'path':'/',**shape(info),'mount_point_by_device_change':True})
        prefix='';device=info.st_dev
        for part in PurePosixPath(path).parts[1:]:
            prefix+='/'+part;check();named=host.lstat(part,fd)
            rows.append({'path':prefix,**shape(named),'mount_point_by_device_change':named.st_dev!=device})
            need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT')
            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')
            device=held.st_dev
        check();return fd
    except BaseException:
        host.close(fd);raise

def enter(ctx,fd,name):
    """One named directory below an open one, never through a link. (None,None): absent. (stat,None): not a directory."""
    host=ctx.host;ctx.check()
    try:named=host.lstat(name,fd)
    except FileNotFoundError:return None,None
    if not stat.S_ISDIR(named.st_mode):return named,None
    ctx.check();opened=host.open(name,DIRECTORY|host.noatime(),dir_fd=fd)
    try:
        held=host.fstat(opened);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')
    except BaseException:
        host.close(opened);raise
    return named,opened

def peek(ctx,fd,name):
    """lstat of one name below an open directory; None when it is absent."""
    host=ctx.host;ctx.check()
    try:return host.lstat(name,fd)
    except FileNotFoundError:return None

def filesystem(host,fd):
    info=host.fstat(fd);v=host.fstatvfs(fd)
    values=(v.f_frsize,v.f_blocks,v.f_bfree,v.f_bavail,v.f_files,v.f_favail,v.f_flag)
    need(all(type(value) is int and value>=0 for value in values) and v.f_frsize>0,'STATVFS_INVALID')
    major,minor=linux_device(info.st_dev)
    return {'status':'COMPLETE','device':info.st_dev,'device_major':major,'device_minor':minor,'inode':info.st_ino,
            'f_frsize':v.f_frsize,'f_blocks':v.f_blocks,'f_bfree':v.f_bfree,'f_bavail':v.f_bavail,'f_files':v.f_files,
            'f_favail':v.f_favail,'read_only':bool(v.f_flag&1),'bytes_total':v.f_blocks*v.f_frsize,
            'bytes_free_for_root_f_bfree':v.f_bfree*v.f_frsize,
            'bytes_available_to_non_root_f_bavail':v.f_bavail*v.f_frsize}

def read_bounded(host,fd,limit):
    raw=b''
    while len(raw)<=limit:
        block=host.read(fd,limit+1-len(raw))
        if not block:break
        raw+=block
    need(len(raw)<=limit,'CONTENT_SIZE_LIMIT');return raw

def read_small(ctx,fd,name,limit):
    """Bounded content of one regular file named below an open directory: (facts, bytes or None). A link, a directory
    or a special file is reported by type and never opened; an absent file is a fact."""
    host=ctx.host;info=peek(ctx,fd,name)
    if info is None:return {'status':'COMPLETE','exists':False},None
    if not stat.S_ISREG(info.st_mode):
        return {'status':'COMPLETE','exists':True,**leaf(info),'mtime_epoch':seconds(info),'content_read':False},None
    ctx.check();opened=host.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|host.noatime(),dir_fd=fd)
    try:
        # The facts are those of the descriptor that is read: these files are replaced by rename, never rewritten in place.
        held=host.fstat(opened);need(stat.S_ISREG(held.st_mode),'PATH_CHANGED');need(held.st_size<=limit,'CONTENT_SIZE_LIMIT')
        raw=read_bounded(host,opened,limit)
    finally:host.close(opened)
    return {'status':'COMPLETE','exists':True,**leaf(held),'mtime_epoch':seconds(held),'content_read':True},raw

def read_at(ctx,directory,name,limit):
    """read_small below a fixed directory; a missing directory is the fact that the file is absent."""
    rows=[];guarded(ctx,directory+'/'+name)
    with Held(ctx.host) as held:
        try:fd=held.keep(descend(ctx.host,directory,ctx.check,rows))
        except FileNotFoundError:return {'status':'COMPLETE','exists':False},None
        return read_small(ctx,fd,name,limit)

def unread(facts,raw):
    """A path that exists and is not a regular file is never opened: its content was NOT observed, and that is a failed
    observation, not a fact about the content."""
    return dict(facts,status='UNAVAILABLE',code='NOT_A_REGULAR_FILE') if facts.get('exists') and raw is None else None

def census(ctx,fd,classify=None,live=False,cap_is_problem=False):
    """Aggregates of the immediate entries of an open directory: (facts, dates). A name lives only in the loop
    variable and in the argument of classify, which answers with fixed labels and, for a label with a date, the
    validated date. No name is stored, returned or emitted."""
    host=ctx.host;before=host.fstat(fd);count=0;capped=False;vanished=0;groups={};labels={};dates={}
    totals={name:0 for name in COUNTERS}
    for name in host.names(fd):
        if count>=CENSUS_CAP:capped=True;break
        count+=1
        if count%64==0:ctx.check()
        try:info=host.lstat(name,fd)
        except FileNotFoundError:vanished+=1;continue
        mode=stat.S_IMODE(info.st_mode);form=kind(info.st_mode)
        key=(form,info.st_uid,info.st_gid,'%04o'%mode);groups[key]=groups.get(key,0)+1
        if form=='symlink':totals['symlink']+=1
        else:
            may=access(info)
            totals['not_uid0']+=info.st_uid!=0
            totals['private_not_uid0']+=info.st_uid!=0 and mode&0o077==0
            totals['not_private']+=mode&0o077!=0
            totals['group_other_writable']+=mode&0o022!=0
            totals['uid0_nocap_unreadable']+=not (may['read'] and (form!='dir' or may['search_or_execute']))
        if classify is not None:
            for label,day in classify(name,info):
                labels[label]=labels.get(label,0)+1
                if day is not None and len(dates.setdefault(label,set()))<MAX_DATES:dates[label].add(day)
    ordered=sorted(groups.items(),key=lambda item:(-item[1],item[0]))
    rows=[list(key)+[number] for key,number in ordered[:HISTOGRAM_ROWS]]          # columns: HISTOGRAM_COLUMNS
    unchanged=before.st_atime_ns==host.fstat(fd).st_atime_ns;issues=[]
    if capped and cap_is_problem:issues.append('CENSUS_CAPPED')
    if not unchanged and not live:issues.append('ATIME_CHANGED_DURING_LISTING')
    facts={'status':'COMPLETE' if not issues else 'PARTIAL','issues':issues,'count':count,'capped':capped,
           'vanished_count':vanished,'atime_unchanged':unchanged,'histogram':rows,
           'histogram_other_entries':sum(number for _,number in ordered[HISTOGRAM_ROWS:]),
           'counters':{name:value for name,value in totals.items() if value}}
    if live:facts['live_directory']=True
    if classify is not None:facts['classes']=labels
    return facts,dates

def document(raw,limit,code):
    try:return decode(raw,limit)
    except Refused:raise Refused(code)

def day_of(value):
    try:return datetime.strptime(value,'%Y-%m-%d').date().isoformat()
    except ValueError:return None


def mount_table(ctx):
    """One bounded read of this process's mountinfo. Rows stay in memory; holder() reduces one of them to fixed fields."""
    host=ctx.host
    with Held(host) as held:
        ctx.check();proc=held.keep(host.open('/proc',DIRECTORY))
        ctx.check();own=held.keep(host.open(str(host.pid()),DIRECTORY,dir_fd=proc))
        ctx.check();fd=held.keep(host.open('mountinfo',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=own))
        raw=read_bounded(host,fd,MOUNTINFO_LIMIT)
    def plain(value):return re.sub(r'\\([0-7]{3})',lambda match:chr(int(match.group(1),8)),value)
    rows=[]
    for line in raw.decode('utf-8','replace').split('\n'):
        if not line:continue
        left,separator,right=line.partition(' - ');fields=left.split(' ');tail=right.split(' ');major,colon,minor=(fields+['','',''])[2].partition(':')
        # A line of another shape is skipped: only the holder of a fixed path is looked for, and a missing holder is reported.
        if separator!=' - ' or len(fields)<6 or len(tail)<2 or colon!=':' or not (text(major,'[0-9]{1,9}') and text(minor,'[0-9]{1,9}')):continue
        rows.append({'device':(int(major),int(minor)),'root':plain(fields[3]),'mount_point':plain(fields[4]),
                     'options':fields[5].split(','),'fstype':tail[0],'source':plain(tail[1])})
    need(rows,'MOUNTINFO_INVALID');return rows

def automounts(table):
    """(number of autofs rows, mount points whose LAST row is autofs: nothing is mounted over them yet)."""
    last={};rows=0
    for row in table:
        last[row['mount_point']]=row['fstype'];rows+=row['fstype']=='autofs'
    return rows,tuple(sorted(point for point,form in last.items() if form=='autofs'))

def holder(table,path,facts):
    """The mount that holds a fixed path. The mount point is a prefix of that signed path, so it carries no new name."""
    if type(table) is not list:return {'status':'UNAVAILABLE','code':table.get('code','MOUNTINFO_UNAVAILABLE')}
    found=None
    for row in table:
        if below(path,row['mount_point']) and (found is None or len(row['mount_point'])>=len(found['mount_point'])):found=row
    if found is None:return {'status':'UNAVAILABLE','code':'MOUNT_HOLDER_NOT_FOUND'}
    out={'status':'COMPLETE','mount_point':found['mount_point'],'mount_point_is_the_path':found['mount_point']==path,
         'mounted_root_is_the_filesystem_root':found['root']=='/','filesystem_type':token(found['fstype'],FILESYSTEM_TYPES),
         'source_device':found['source'] if text(found['source'],DEVICE_PATTERN) else None,
         'read_write':'rw' in found['options'],
         'device_equals_the_directory_device':found['device']==(facts['device_major'],facts['device_minor'])}
    out['source_device_withheld']=out['source_device'] is None
    return out


def runtime(ctx):
    host=ctx.host
    def python():
        version,implementation=host.python()
        need(type(version) is tuple and len(version)==3 and all(type(part) is int and 0<=part<1000 for part in version),
             'RUNTIME_FIELD_INVALID')
        return {'status':'COMPLETE','major':version[0],'minor':version[1],'micro':version[2],
                'implementation':token(implementation,['cpython'])}
    def kernel():
        # The release is read from procfs so that the node name of uname never enters this process.
        guarded(ctx,KERNEL_RELEASE);parts=PurePosixPath(KERNEL_RELEASE).parts
        with Held(host) as held:
            ctx.check();fd=held.keep(host.open('/'+parts[1],DIRECTORY))
            for part in parts[2:-1]:
                ctx.check();fd=held.keep(host.open(part,DIRECTORY,dir_fd=fd))
            ctx.check();fd=held.keep(host.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd))
            raw=read_bounded(host,fd,KERNEL_RELEASE_LIMIT)
        try:found=dotted(raw.decode('ascii').rstrip('\n'))
        except UnicodeDecodeError:found=None
        if found is None:return {'status':'COMPLETE','version':None,'abi':None,'release_withheld':True}
        abi=re.match(r'-([0-9]{1,6})(?![0-9])',found[1])
        return {'status':'COMPLETE','version':found[0],'abi':int(abi.group(1)) if abi else None,'release_withheld':False,
                'suffix_withheld':found[1][abi.end() if abi else 0:]!=''}
    def boot():
        uptime,now=host.uptime(),host.now()
        need(type(uptime) in (int,float) and type(now) in (int,float) and 0<=uptime<now,'RUNTIME_FIELD_INVALID')
        return {'status':'COMPLETE','uptime_seconds':int(uptime),'boot_epoch_utc':int(now-uptime),
                'basis':'CLOCK_BOOTTIME subtracted from the wall clock; a later read with a larger value proves a reboot'}
    items={'python':attempt(python),'kernel':attempt(kernel),'boot':attempt(boot)}
    return finish(dict(items),items.values())

def docker_daemon(ctx):
    value=strict(ctx.output('version'))
    # A CLI that cannot reach the daemon may print a zero value and exit 0: an empty version is no answer, never a fact.
    need(type(value) is str and value!='','DAEMON_VERSION_EMPTY')
    found=dotted(value);need(found is not None,'DAEMON_FIELD_INVALID')
    return {'status':'COMPLETE','server_version':found[0],'server_version_suffix_withheld':found[1]!='',
            'docker_path':ctx.path('docker'),'docker_endpoint':DOCKER_ENDPOINT,'docker_info_requested':False}

def family_facts(ctx,reference):
    """One validated row of metadata. Environment is never requested; network details are reduced to names."""
    row=decode(ctx.output('family',reference))
    keys={'name','id','image_id','image_reference','running','state','started_at','host_pid','restarts','project','service',
          'oneoff','revision','user','userns_mode','readonly_rootfs','network_mode','networks','mounts'}
    need(set(row)==keys and row['id']==reference and text(row['name'],'/'+NAME) and text(row['image_id'],IMAGE_ID)
         and text(row['image_reference'],REFERENCE) and type(row['running']) is bool and row['state'] in STATES
         and text(row['started_at'],STAMP) and type(row['host_pid']) is int and row['host_pid']>=0
         and type(row['restarts']) is int and row['restarts']>=0 and row['project']==PROJECT and row['service'] in SERVICES
         and type(row['networks']) is list and row['networks'] and row['networks'][-1] is None
         and type(row['mounts']) is list and row['mounts'] and row['mounts'][-1] is None,'FAMILY_METADATA_INVALID')
    # The daemon builds Mounts by ranging over a map: the order differs between two reads of an unchanged container.
    # This was the single cause of the three problems of the read of 2026-10-02. Both lists are compared in canonical order.
    for key in ('mounts','networks'):row[key]=sorted(row[key][:-1],key=canonical)+[None]
    return row

def volume_name(source):
    match=re.fullmatch(re.escape(VOLUME_ROOT)+'/('+NAME+')/_data',source) if type(source) is str else None
    return match.group(1) if match and match.group(1) in VOLUMES else None

def family_row(row,candidates):
    """Reduce a validated raw row to emitted fields. Every text that is emitted comes from a fixed allow-list; anything
    else is replaced by OTHER or withheld and flagged."""
    issues=[];findings=[]
    def listed(key,allowed,code):
        if row[key] is None or (type(row[key]) is str and row[key] in allowed):return row[key]
        findings.append(code);return 'OTHER'
    conforming=re.fullmatch('/'+PROJECT+'-'+re.escape(row['service'])+'-[0-9]{1,2}',row['name']) is not None
    out={'name':row['name'][1:] if conforming else None,'name_conforming':conforming,'image_id':row['image_id'],
         'image_reference':listed('image_reference',IMAGE_TAGS,'IMAGE_REFERENCE_OUTSIDE_ALLOW_LIST'),
         'running':row['running'],'state':row['state'],'started_at':row['started_at'],'restarts':row['restarts'],
         'userns_mode':listed('userns_mode',USERNS_MODES,'USERNS_MODE_OUTSIDE_ALLOW_LIST'),
         'network_mode':listed('network_mode',NETWORK_MODES,'NETWORK_MODE_OUTSIDE_ALLOW_LIST')}
    revision=row['revision']
    if not (revision in (None,'') or text(revision,HEX40)):revision=None;issues.append('REVISION_LABEL_INVALID')
    out['revision_label']=revision
    user=row['user']
    if not (user in (None,'') or text(user,'[0-9]{1,10}(:[0-9]{1,10})?')):user=None;findings.append('USER_NOT_NUMERIC')
    out['user']=user
    out['readonly_rootfs']=row['readonly_rootfs'] if type(row['readonly_rootfs']) is bool or row['readonly_rootfs'] is None else None
    if out['readonly_rootfs'] is not row['readonly_rootfs']:issues.append('READONLY_ROOTFS_INVALID')
    networks=row['networks'][:-1];known=sorted(value for value in networks if type(value) is str and value in NETWORKS)
    out['networks']=known;out['networks_other_count']=len(networks)-len(known)
    if len(networks)>MAX_NETWORKS:issues.append('NETWORK_LIMIT')
    mounts=[];data=[];capacity=[];data_invalid=False
    for item in row['mounts'][:-1]:
        ok=(type(item) is dict and set(item)=={'type','source','destination','rw'} and item['type'] in MOUNT_TYPES
            and (item['source'] in (None,'') or clean_path(item['source'])) and clean_path(item['destination'])
            and type(item['rw']) is bool)
        targeted=type(item) is dict and item.get('destination')==DATA_DESTINATION
        if ok and targeted and data_path(item['source']):data.append(item)
        elif targeted:data_invalid=True
        if ok and item['destination']==CAPACITY_DESTINATION:capacity.append(item)
        if not ok:
            mounts.append({'withheld':True});issues.append('MOUNT_INVALID');continue
        source=item['source'];candidate=source in candidates;volume=volume_name(source)
        view={'type':item['type'],'rw':item['rw'],'destination':item['destination'] if item['destination'] in MOUNT_DESTINATIONS else None}
        if volume:view['volume']=volume
        elif candidate:view['source_capacity_candidate_index']=candidates.index(source)
        else:view['source']=source if source in MOUNT_SOURCES else None
        if view['destination'] is None:view['destination_withheld']=True
        if view.get('source',source) is None and source not in (None,''):view['source_withheld']=True
        if view.get('destination_withheld') or view.get('source_withheld'):findings.append('MOUNT_OUTSIDE_ALLOW_LIST')
        mounts.append(view)
    if data_invalid:issues.append('DATA_MOUNT_INVALID')
    if len(data)>1:issues.append('DATA_MOUNT_DUPLICATED')
    if len(capacity)>1:issues.append('CAPACITY_MOUNT_DUPLICATED')
    if len(mounts)>MAX_MOUNTS:issues.append('MOUNT_LIMIT')
    mounts.sort(key=lambda item:(str(item.get('destination')),str(item.get('volume',item.get('source'))),str(item.get('type'))))
    out['mount_count']=len(mounts);out['mounts']=mounts[:MAX_MOUNTS];out['has_data_mount']=bool(data) or data_invalid
    if row['restarts']:findings.append('RESTARTS_NONZERO')
    if not row['running']:findings.append('CONTAINER_NOT_RUNNING')
    return out,issues,findings,data,capacity,data_invalid

def containers(ctx,candidates):
    def listing():
        rows=[decode(line) for line in ctx.output('ps').splitlines() if line]
        need(len(rows)<=MAX_LISTED,'CONTAINER_COUNT_LIMIT')
        for row in rows:
            need(set(row)=={'id','name','state'} and text(row['id'],HEX64) and text(row['name'],NAME)
                 and row['state'] in STATES,'CONTAINER_LIST_INVALID')
        need(len({row['id'] for row in rows})==len(rows),'CONTAINER_LIST_DUPLICATE')
        return sorted(rows,key=lambda row:row['id'])
    before=listing();issues=[];findings=[];family=[];outside=0;outside_running=0;other=0;unclassified=0
    per={service:{'count':0,'running':0,'oneoff_count':0} for service in SERVICES}
    for listed in before:
        try:
            item=decode(ctx.output('class',listed['id']))
            need(set(item)=={'id','running','project','service','oneoff'} and item['id']==listed['id'] and type(item['running']) is bool
                 and all(item[key] is None or (type(item[key]) is str and len(item[key])<=256) for key in ('project','service','oneoff')),
                 'CLASS_INVALID')
        except Exception:unclassified+=1;continue
        if item['project']!=PROJECT:
            outside+=1;outside_running+=item['running']
        elif item['service'] in SERVICES:
            family.append(item);entry=per[item['service']]
            if item['oneoff']=='True':entry['oneoff_count']+=1
            else:
                entry['count']+=1;entry['running']+=item['running']
        else:other+=1
    if unclassified:issues.append('UNCLASSIFIED_CONTAINERS')
    family.sort(key=lambda item:(item['service'],item['id']))
    if len(family)>MAX_FAMILY:issues.append('FAMILY_LIMIT')
    # The data source is the mount of the RUNNING containers that are not one-off. One of those that could not be
    # classified or read may carry the data mount: the mount facts are then incomplete. What a stopped or one-off
    # container mounts is kept apart (others) and can only raise a finding.
    rows=[];carriers=[];others=[];raw={};incomplete=bool(unclassified) or len(family)>MAX_FAMILY
    for item in family[:MAX_FAMILY]:
        # 'running' is the answer of the class read until the family read replaces it: a row whose family read fails
        # is still known to be a running container, and no section may take it for a missing one.
        row={'status':'UNAVAILABLE','service':item['service'],'oneoff':item['oneoff']=='True','container_id':item['id'],
             'running':item['running']}
        relevant=item['running'] and item['oneoff']!='True'
        try:
            first=family_facts(ctx,item['id']);facts,problems,found,data,capacity,data_invalid=family_row(first,candidates)
            row.update(facts);relevant=relevant or (first['running'] and item['oneoff']!='True')
            incomplete=incomplete or (relevant and (data_invalid or len(data)>1))
            second=family_facts(ctx,item['id']);changed=sorted(key for key in first if first[key]!=second[key])
            row['unchanged_during_read']=not changed;row['changed_keys']=changed
            if changed:problems.append('CONTAINER_CHANGED');incomplete=incomplete or relevant
            row['issues']=sorted(set(problems));row['findings']=sorted(set(found));row['status']='COMPLETE' if not problems else 'PARTIAL'
            if not changed:
                raw[item['id']]={'data':data,'capacity':capacity}
                if len(data)==1 and not data_invalid:
                    (carriers if first['running'] and item['oneoff']!='True' else others).append(
                        {'service':item['service'],'type':data[0]['type'],'source':data[0]['source'],'rw':data[0]['rw']})
        except Exception as error:
            row.update(safe(error));incomplete=incomplete or relevant
        rows.append(row)
    after=attempt(listing);stable=after==before
    if not stable:issues.append('LIST_UNSTABLE')
    # Why the sections that count or compare containers cannot give a negative answer, if they cannot.
    unknown=('UNCLASSIFIED_CONTAINERS' if unclassified else 'FAMILY_LIMIT' if len(family)>MAX_FAMILY else 'FAMILY_EMPTY' if not rows
             else None if stable else 'LIST_UNSTABLE')
    incomplete=incomplete or unknown is not None
    missing=sorted(name for name in SERVICES if per[name]['count']==0)
    duplicated=sorted(name for name in SERVICES if per[name]['count']>1)
    stopped=sorted(name for name in SERVICES if per[name]['count']>per[name]['running'])
    fixed={name:{'present':False,'state':None} for name in FIXED_CONTAINER_NAMES}
    for listed in before:
        if listed['name'] in fixed:fixed[listed['name']]={'present':True,'state':listed['state']}
    if missing and unknown is None:findings.append('SERVICE_MISSING')
    if duplicated:findings.append('SERVICE_DUPLICATED')
    if stopped:findings.append('SERVICE_CONTAINER_NOT_RUNNING')
    if any(entry['oneoff_count'] for entry in per.values()):findings.append('ONEOFF_CONTAINER_PRESENT')
    if any(entry['present'] for entry in fixed.values()):findings.append('FIXED_NAME_CONTAINER_PRESENT')
    if any(row['status']!='COMPLETE' for row in rows):issues.append('FAMILY_ROW_INCOMPLETE')
    if not rows:issues.append('FAMILY_EMPTY')
    section={'status':'UNAVAILABLE' if not rows else 'COMPLETE' if not issues else 'PARTIAL','issues':sorted(set(issues)),
             'findings':sorted(set(findings)),'listed_before':len(before),'listed_after':len(after) if type(after) is list else None,
             'list_stable':stable,'services':per,'rows':rows,'row_count':len(family),
             'services_missing':missing if unknown is None else None,
             'services_duplicated':duplicated,'services_with_a_container_not_running':stopped,'stack_other_services_count':other,
             'outside_stack_count':outside,'running_outside_stack_count':outside_running,'unclassified_count':unclassified,
             'fixed_names':fixed,'environment_requested':False}
    if not rows:section['code']='FAMILY_EMPTY'
    return section,{'observed':True,'rows':rows,'raw':raw,'per':per,'carriers':carriers,'others':others,'incomplete':incomplete,
                    'unknown':unknown}

def steady(shared,service,running=True):
    return [row for row in shared['rows'] if row['service']==service and not row['oneoff'] and (row.get('running') is True or not running)]

def agreement(shared,services,key,expected):
    """Whether every running container of these services carries the expected value, in three values and with the
    reason. False: one that was read differs. None with a code: one could not be read, classified or counted, so 'every'
    cannot be answered. None without a code: none of them is running. True otherwise."""
    rows=[row for name in services for row in steady(shared,name)]
    read=[row for row in rows if 'image_id' in row]
    if any(row.get(key)!=expected for row in read):return False,None
    if shared['unknown']:return None,shared['unknown']
    if len(read)<len(rows):return None,'CONTAINER_ROW_UNAVAILABLE'
    return (True if rows else None),None

def worker(shared,candidates):
    need(shared['observed'],'CONTAINERS_UNOBSERVED')
    summary=shared['per'][WORKER];findings=[];rows=[];unknown=shared['unknown'];issues=[unknown] if unknown else []
    exactly=summary['count']==1 and summary['running']==1
    # A container that was not classified or counted may be a worker: one known worker is then not 'exactly one'.
    if unknown and summary['count']<=1:exactly=None
    if exactly is False:findings.append('WORKER_COUNT_NOT_ONE')
    listed=steady(shared,WORKER,running=False)
    if len(listed)>MAX_WORKERS:issues.append('WORKER_LIMIT')
    for row in listed[:MAX_WORKERS]:
        entry=shared['raw'].get(row['container_id'])
        if entry is None:
            rows.append({'status':'UNAVAILABLE','code':'WORKER_ROW_UNAVAILABLE','container_id':row['container_id']});continue
        item={'status':'COMPLETE','container_id':row['container_id'],'running':row.get('running')}
        mounts=entry['capacity']
        if len(mounts)!=1:
            item['capacity_mount']={'present':bool(mounts),'count':len(mounts)};findings.append('CAPACITY_MOUNT_ABSENT' if not mounts else 'CAPACITY_MOUNT_DUPLICATED')
        else:
            mount=mounts[0];volume=volume_name(mount['source']);candidate=mount['source'] in candidates
            item['capacity_mount']={'present':True,'count':1,'type':mount['type'],'rw':mount['rw'],'volume':volume,
                                    'is_the_unprovisioned_placeholder':volume==CAPACITY_PLACEHOLDER,
                                    'source_capacity_candidate_index':candidates.index(mount['source']) if candidate else None}
            if mount['rw']:findings.append('CAPACITY_MOUNT_WRITABLE')
            if mount['type']=='bind':findings.append('CAPACITY_MOUNT_IS_BIND' if candidate else 'CAPACITY_MOUNT_BIND_SOURCE_NOT_A_CANDIDATE')
            elif volume!=CAPACITY_PLACEHOLDER:findings.append('CAPACITY_MOUNT_VOLUME_NOT_THE_PLACEHOLDER')
        data=entry['data']
        item['data_mount']={'present':len(data)==1,'type':data[0]['type'] if len(data)==1 else None,
                            'rw':data[0]['rw'] if len(data)==1 else None,
                            'source_in_data_sources':data[0]['source'] in DATA_SOURCES if len(data)==1 else None}
        if len(data)!=1:findings.append('WORKER_DATA_MOUNT_ABSENT')
        rows.append(item)
    out={'count':summary['count'],'running':summary['running'],'oneoff_count':summary['oneoff_count'],
         'exactly_one_running':exactly,'workers':rows,
         'basis':'the host .env is never opened: an unset or set capacity source is inferred from the mount type'}
    return finish(out,rows,issues=issues,findings=findings)

def worker_environment(ctx,shared):
    need(shared['observed'],'CONTAINERS_UNOBSERVED')
    def state(present,key,literal,word):
        return 'ABSENT' if key not in present else word if literal in present else 'SET_OTHER'
    def one(reference):
        row=decode(ctx.output('envflags',reference,failure='ENVFLAGS_COMMAND_FAILED'))
        need(set(row)=={'id','flags'} and row['id']==reference and type(row['flags']) is list and 0<len(row['flags'])<=MAX_FLAGS
             and row['flags'][-1] is None and all(type(value) is str and value in ENV_TOKENS for value in row['flags'][:-1]),
             'ENVFLAGS_INVALID')
        present=set(row['flags'][:-1]);findings=[]
        if 'DATABASE_URL_KEY' not in present:findings.append('DATABASE_URL_KEY_ABSENT')
        elif 'DATABASE_URL_EMPTY' in present:findings.append('DATABASE_URL_EMPTY')
        return {'status':'COMPLETE','container_id':reference,'findings':findings,'token_count':len(row['flags'])-1,
                'database_url':state(present,'DATABASE_URL_KEY','DATABASE_URL_EMPTY','EMPTY').replace('SET_OTHER','SET'),
                'capacity_required':state(present,'CAPACITY_REQUIRED_KEY','CAPACITY_REQUIRED_TRUE','TRUE'),
                'capacity_veto_mode':state(present,'CAPACITY_VETO_MODE_KEY','CAPACITY_VETO_MODE_DOCUMENTED','DOCUMENTED'),
                'shadow_enabled':state(present,'SHADOW_ENABLED_KEY','SHADOW_ENABLED_TRUE','TRUE'),
                'massive_bars_enabled':state(present,'MASSIVE_BARS_ENABLED_KEY','MASSIVE_BARS_ENABLED_TRUE','TRUE'),
                'shadow_source_dir':state(present,'SHADOW_SOURCE_DIR_KEY','SHADOW_SOURCE_DIR_IS_CANDIDATE','CANDIDATE'),
                'massive_journal_dir':state(present,'MASSIVE_JOURNAL_DIR_KEY','MASSIVE_JOURNAL_DIR_EMPTY','EMPTY').replace('SET_OTHER','SET'),
                'raw_dir':state(present,'RAW_DIR_KEY','RAW_DIR_DOCUMENTED','DOCUMENTED'),
                'keys_present':{name:name in present for _,name in ENV_KEYS}}
    targets=[row['container_id'] for row in steady(shared,WORKER)]
    rows=[]
    for reference in targets[:MAX_WORKERS]:
        item=attempt(lambda reference=reference:one(reference));item.setdefault('container_id',reference);rows.append(item)
    out={'evaluated_count':len(rows),'workers':rows,'values_in_this_process':0,
         'basis':'fixed tokens printed by the Docker CLI for fixed keys and fixed literal lines; SET_OTHER means the key is present '
                 'with another value, which this process never receives'}
    unknown=shared['unknown'];issues=(['WORKER_LIMIT'] if len(targets)>MAX_WORKERS else [])+([unknown] if unknown else [])
    # 'No running worker' is a fact only when every listed container was classified and counted.
    return finish(out,rows,issues=issues,findings=[] if rows or unknown else ['NO_RUNNING_WORKER_TO_EVALUATE'])

def network(ctx,shared):
    need(shared['observed'],'CONTAINERS_UNOBSERVED')
    def attachment(reference):
        row=decode(ctx.output('attach',reference,failure='ATTACH_COMMAND_FAILED'))
        need(set(row)=={'id','networks'} and row['id']==reference and type(row['networks']) is list
             and 0<len(row['networks'])<=MAX_NETWORKS+1 and row['networks'][-1] is None,'ATTACH_INVALID')
        found={};other=0
        for item in row['networks'][:-1]:
            need(type(item) is dict and set(item)=={'name','network_id'} and type(item['name']) is str,'ATTACH_INVALID')
            if item['name'] in NETWORKS:
                need(text(item['network_id'],HEX64),'ATTACH_INVALID');found[item['name']]=item['network_id']
            else:other+=1
        return {'status':'COMPLETE','evaluated':True,'network_ids':found,'other_network_count':other,
                'on_compose_network':COMPOSE_NETWORK in found}
    def inspect():
        row=decode(ctx.output('network',failure='NETWORK_COMMAND_FAILED'))
        members=row.get('containers')
        need(set(row)=={'name','driver','scope','internal','attachable','containers'} and row['name']==COMPOSE_NETWORK
             and type(row['internal']) is bool and type(row['attachable']) is bool and type(members) is list
             and 0<len(members)<=MAX_LISTED+1 and members[-1] is None and all(type(value) is str for value in members[:-1]),
             'NETWORK_INVALID')
        ids={value for value in members[:-1] if text(value,HEX64)}
        return {'status':'COMPLETE','name':COMPOSE_NETWORK,'driver':token(row['driver'],NETWORK_DRIVERS),
                'scope':token(row['scope'],NETWORK_SCOPES),'internal':row['internal'],'attachable':row['attachable'],
                'attached_count':len(members)-1,'attached_not_a_container_id_count':len(members)-1-len(ids)},ids
    findings=[];attachments={};ids=None;unknown=shared['unknown'];issues=[unknown] if unknown else []
    for label,service in (('db',DATABASE),('worker',WORKER)):
        rows=steady(shared,service)
        attachments[label]=(attempt(lambda reference=rows[0]['container_id']:attachment(reference)) if rows
                            else {'status':'COMPLETE','evaluated':False})
    try:facts,ids=inspect()
    except Exception as error:facts=safe(error)
    seen=sorted({item['network_ids'][COMPOSE_NETWORK] for item in attachments.values() if item.get('on_compose_network')})
    out={'inspect':facts,'attachments':attachments,'network_id':seen[0] if len(seen)==1 else None,'network_ids_agree':len(seen)<=1,
         'db_attached_by_network_inspect':None,'worker_attached_by_network_inspect':None,'backend_attached_count':None,
         'reachability_from_a_container_outside_compose':'NOT_OBSERVED_HERE'}
    if ids is not None:
        def attached(service):
            rows=steady(shared,service)
            if not rows:return None if unknown else False
            return all(row['container_id'] in ids for row in rows)
        out['db_attached_by_network_inspect']=attached(DATABASE);out['worker_attached_by_network_inspect']=attached(WORKER)
        out['backend_attached_count']=sum(1 for name in BACKEND for row in steady(shared,name) if row['container_id'] in ids)
    if not attachments['db'].get('evaluated'):
        if attachments['db'].get('status')=='COMPLETE' and not unknown:findings.append('DB_CONTAINER_NOT_RUNNING')
    elif not attachments['db']['on_compose_network']:findings.append('DB_NOT_ON_NETWORK')
    if attachments['worker'].get('evaluated') and not attachments['worker']['on_compose_network']:findings.append('WORKER_NOT_ON_NETWORK')
    if len(seen)>1:findings.append('NETWORK_ID_DISAGREE')
    if out['db_attached_by_network_inspect'] is False and attachments['db'].get('evaluated'):findings.append('DB_NOT_ON_NETWORK')
    return finish(out,[facts]+list(attachments.values()),issues=issues,findings=findings)

def images(ctx,shared):
    def one(reference,mandatory):
        try:raw=ctx.output('image',reference)
        except CommandFailed as error:
            # Exit status 1 is what the CLI answers for a reference that does not resolve, and also for an error of the
            # daemon. It is read as 'the tag does not exist' only for a tag that is not mandatory, and only when the
            # daemon resolved the production tag in this same run; otherwise it is a failed observation.
            if error.returncode!=1:raise
            if mandatory:raise CommandFailed('IMAGE_UNRESOLVED',1)
            return {'status':'COMPLETE','resolved':False}
        row=decode(raw);tags=row.get('repo_tags')
        need(set(row)=={'id','repo_tags','revision'} and text(row['id'],IMAGE_ID)
             and (tags is None or (type(tags) is list and all(type(tag) is str for tag in tags))),'IMAGE_METADATA_INVALID')
        need(not text(reference,IMAGE_ID) or row['id']==reference,'IMAGE_METADATA_INVALID')
        allowed=sorted({tag for tag in tags or [] if tag in IMAGE_TAGS});issues=[];revision=row['revision']
        retention=sum(1 for tag in tags or [] if text(tag,RETENTION_TAG_PATTERN))
        if not (revision in (None,'') or text(revision,HEX40)):revision=None;issues.append('REVISION_LABEL_INVALID')
        return {'status':'COMPLETE' if not issues else 'PARTIAL','issues':issues,'resolved':True,'id':row['id'],
                'revision_label':revision,'repo_tags':allowed,'retention_tag_count':retention,
                'other_tag_count':len(tags or [])-len(allowed)-retention}
    tags={MANDATORY_TAG:attempt(lambda:one(MANDATORY_TAG,True))};answered=tags[MANDATORY_TAG].get('resolved') is True
    for reference in IMAGE_TAGS:
        if reference!=MANDATORY_TAG:tags[reference]=attempt(lambda reference=reference:one(reference,not answered))
    known={item['id'] for item in tags.values() if item.get('resolved')}
    wanted=sorted({row['image_id'] for row in shared['rows'] if text(row.get('image_id'),IMAGE_ID)}-known)
    by_id=[]
    for image_id in wanted[:MAX_IMAGES]:
        item=attempt(lambda image_id=image_id:one(image_id,True));item.setdefault('id',image_id);by_id.append(item)
    findings=[];issues=['IMAGE_LIMIT'] if len(wanted)>MAX_IMAGES else []
    production=tags[MANDATORY_TAG];rollback=tags['c3po/backend:rollback']
    backend=[row for name in BACKEND for row in steady(shared,name) if 'image_id' in row]
    out={'tags':tags,'stack_images_without_a_listed_tag':by_id,'stack_image_count_without_a_listed_tag':len(wanted),
         'backend_containers_compared':len(backend),'backend_image_ids_distinct':len({row['image_id'] for row in backend}),
         'backend_services_without_a_running_container':None,
         'production_id_equals_every_running_backend':None,'revision_label_equal_across_backend_and_production':None,
         'rollback_differs_from_production':None,'service_tag_equals_running':{},
         'identification_basis':'the '+REVISION_LABEL+' label; the local ID is specific to this image store and is the only ID '
                                'that may be rendered into a unit'}
    if shared['observed'] and not shared['unknown']:
        idle=sorted(name for name in BACKEND if not steady(shared,name));out['backend_services_without_a_running_container']=idle
        if idle:findings.append('BACKEND_SERVICE_WITHOUT_RUNNING_CONTAINER')
    if production.get('resolved') and shared['observed']:
        # Only the containers that run are compared; a service without one is reported apart, just above.
        same,why=agreement(shared,BACKEND,'image_id',production['id']);out['production_id_equals_every_running_backend']=same
        if same is False:findings.append('PRODUCTION_TAG_NOT_RUNNING_IMAGE')
        if why:issues.append(why)
        label=production.get('revision_label')
        same,why=(False,None) if label in (None,'') else agreement(shared,BACKEND,'revision_label',label)
        out['revision_label_equal_across_backend_and_production']=same
        if same is False:findings.append('REVISION_LABEL_MISMATCH')
        if why:issues.append(why)
        if rollback.get('status')=='COMPLETE' and rollback['resolved']:
            out['rollback_differs_from_production']=rollback['id']!=production['id']
    for service,reference in sorted(SERVICE_TAG.items()):
        if not shared['observed']:continue
        if tags[reference].get('resolved'):
            same,why=agreement(shared,[service],'image_id',tags[reference]['id'])
            if same is not None:out['service_tag_equals_running'][service]=same
            if same is False:findings.append('SERVICE_TAG_NOT_RUNNING_IMAGE')
            if why:issues.append(why)
        elif tags[reference].get('status')=='COMPLETE' and any(row.get('image_reference')==reference for row in steady(shared,service)):
            # A running container was created from this tag: 'the tag does not exist' is then not an answer to accept.
            issues.append('IMAGE_REFERENCED_TAG_UNRESOLVED')
    return finish(out,list(tags.values())+by_id,issues=issues,findings=findings),production

def deploy_version(ctx,shared,production):
    facts,raw=read_at(ctx,APP_DIR,'.deploy-version',DEPLOY_VERSION_LIMIT);findings=[];issues=[]
    out={'file':facts,'revision':None,'equals_production_revision_label':None,'equals_every_backend_container_revision':None}
    if facts.get('exists') is False:findings.append('DEPLOY_VERSION_ABSENT')
    elif raw is None:findings.append('DEPLOY_VERSION_NOT_A_REGULAR_FILE')
    else:
        match=re.fullmatch(rb'([0-9a-f]{40})\n?',raw);need(match is not None,'DEPLOY_VERSION_INVALID')
        out['revision']=match.group(1).decode('ascii')
        if production.get('resolved'):out['equals_production_revision_label']=production.get('revision_label')==out['revision']
        if shared['observed']:
            same,why=agreement(shared,BACKEND,'revision_label',out['revision']);out['equals_every_backend_container_revision']=same
            if why:issues.append(why)
        if out['equals_production_revision_label'] is False or out['equals_every_backend_container_revision'] is False:
            findings.append('DEPLOY_VERSION_NOT_THE_RUNNING_REVISION')
    return finish(out,[facts],issues=issues,findings=findings)

def root_classifier(today):
    """The name classes of the security controller's trial test (scripts/c3po_security_guard.py), as labels."""
    trial=re.compile(NAME_CLASSES['trial_or_probe']);diagnostic=re.compile(NAME_CLASSES['diagnostic_release'])
    def classify(name,info):
        found=[];link=stat.S_ISLNK(info.st_mode)
        if name.startswith('r2d2-v2-release-'):
            if PurePosixPath(name).suffix=='.json':
                found.append(('release_json',None))
                if link:found.append(('release_json_symlink',None))
                if diagnostic.fullmatch(name):found.append(('release_json_with_a_diagnostic_name',None))
            elif stat.S_ISDIR(info.st_mode):found.append(('release_directory',None))
        if name.startswith(('.r2d2-v2-trial-','.r2d2-v2-probe-')):
            found.append(('trial_or_probe',None));match=trial.fullmatch(name)
            if link:found.append(('trial_or_probe_symlink',None))
            elif not match:found.append(('trial_or_probe_name_unrecognised',None))
            else:
                try:day=datetime.strptime(match.group(1),'%Y%m%d').date().isoformat()
                except ValueError:day=None
                if day is None:found.append(('trial_or_probe_date_invalid',None))
                elif day>=today:found.append(('trial_or_probe_dated_today_or_later',None))
                else:found.append(('trial_or_probe_dated_in_the_past',None))
        if name.startswith('provider=') and stat.S_ISDIR(info.st_mode):found.append(('provider_directory',None))
        if name==PIN_NAME:found.append(('pin',None))
        return found
    return classify

def trial_veto(pin,classes,capped=False):
    """What the controller's trial_present() would answer, clause by clause, without reading a release file and
    without taking the probe lock the controller takes. Under a capped listing a clause that was seen is still
    definite; a clause that was not seen is undetermined."""
    count=lambda label:classes.get(label,0)
    release='NONE' if not count('release_json') else 'SYMLINK' if count('release_json_symlink') else 'UNDETERMINED_WITHOUT_CONTENT'
    other=bool(count('trial_or_probe_name_unrecognised') or count('trial_or_probe_symlink')
               or count('trial_or_probe_dated_today_or_later') or release=='SYMLINK')
    open_question=release=='UNDETERMINED_WITHOUT_CONTENT' or bool(count('trial_or_probe_dated_in_the_past')
                                                                  or count('trial_or_probe_date_invalid'))
    return {'by_pin':pin,'by_release_file':release,'by_unrecognised_name':bool(count('trial_or_probe_name_unrecognised')),
            'by_symlink':bool(count('trial_or_probe_symlink')),'by_current_or_future_date':bool(count('trial_or_probe_dated_today_or_later')),
            'controller_would_fail_on_a_date':bool(count('trial_or_probe_date_invalid')),'by_held_probe_lock':'NOT_EVALUATED',
            'definite':pin or other,'remains_without_the_pin':True if other else 'UNDETERMINED' if open_question or capped else False,
            'listing_capped':capped,
            'basis':'name classes and the pin only; the guard installed on the host is identified by its hash in security_controller'}

def data_volume(ctx,shared,table):
    carriers=shared['carriers'];others=shared.get('others',[])
    distinct=sorted({(item['type'],item['source']) for item in carriers});issues=[];findings=[]
    if shared['incomplete'] or not shared['observed']:issues.append('FAMILY_MOUNT_FACTS_INCOMPLETE')
    source=None;basis=None
    if len(distinct)>1:issues.append('DATA_SOURCE_DISAGREE')
    elif len(distinct)==1:
        if distinct[0][1] in DATA_SOURCES:source,basis=distinct[0][1],'MOUNT_OF_THE_RUNNING_CONTAINERS'
        else:issues.append('DATA_SOURCE_NOT_IN_SCOPE')
    else:
        # No carrier: the signed default is still read, and the receipt says that this is what was done.
        source,basis=DATA_SOURCES[0],'SIGNED_DEFAULT_NO_CARRIER'
        if shared['incomplete'] or not shared['observed']:issues.append('DATA_MOUNT_UNOBSERVED')
        else:findings.append('DATA_MOUNT_NOT_FOUND')
    brief=lambda item:{'service':item['service'],'type':item['type'],'rw':item['rw'],'source_in_data_sources':item['source'] in DATA_SOURCES}
    out={'destination':DATA_DESTINATION,'source':source,'source_basis':basis,'distinct_source_count':len(distinct),
         'carriers':[brief(item) for item in carriers],
         'stopped_or_oneoff_containers_with_the_data_mount':[dict(brief(item),same_source=item['source']==source) for item in others],
         'mount_point_basis':MOUNT_BASIS}
    if source is not None and any(item['source']!=source for item in others):findings.append('STOPPED_CONTAINER_DATA_SOURCE_DIFFERS')
    state={'source':None,'device':None}
    if source is None:return finish(out,[{'status':'UNAVAILABLE'}],issues=issues,findings=findings),state
    rows=[];out['ancestors']=rows
    with Held(ctx.host) as held:
        try:
            guarded(ctx,source,tree=True);fd=held.keep(descend(ctx.host,source,ctx.check,rows))
        except Exception as error:
            out['walk']=safe(error);return finish(out,[out['walk']],issues=issues,findings=findings),state
        info=ctx.host.fstat(fd);may=access(info)
        state['source']=source;out['root_access_as_uid0_without_capabilities']=may;out['root_private']=stat.S_IMODE(info.st_mode)&0o077==0
        # The reader traverses this directory: what it cannot search, and what is private to another uid, is the design refusal.
        if not may['search_or_execute']:findings.append('INPUT_UNREADABLE_UID0_NOCAP')
        if out['root_private'] and info.st_uid!=0:findings.append('PRIVATE_INPUT_NOT_UID0')
        facts=attempt(lambda:filesystem(ctx.host,fd));out['filesystem']=facts
        if facts.get('status')=='COMPLETE':
            state['device']=facts['device'];out['mount']=holder(table,source,facts)
            if facts['read_only']:findings.append('DATA_FILESYSTEM_READ_ONLY')
        else:out['mount']={'status':'UNAVAILABLE','code':'STATVFS_UNAVAILABLE'}
        def root():
            pin=peek(ctx,fd,PIN_NAME);today=datetime.fromtimestamp(ctx.host.now(),timezone.utc).date().isoformat()
            # The veto clauses need the whole listing: a capped one is a problem here.
            listing,_=census(ctx,fd,root_classifier(today),cap_is_problem=True);classes=listing['classes']
            listing['pin']=({'exists':True,**leaf(pin),'mtime_epoch':seconds(pin)} if pin is not None else {'exists':False})
            listing['controller_trial_veto']=trial_veto(pin is not None,classes,listing['capped']);listing['utc_date_of_the_comparison']=today
            return listing
        out['root']=attempt(root)
    veto=out['root'].get('controller_trial_veto')
    if veto:
        state['veto']=veto
        if veto['definite']:findings.append('TRIAL_VETO_PRESENT')
        if veto['remains_without_the_pin'] is True:findings.append('TRIAL_VETO_INDEPENDENT_OF_PIN')
    return finish(out,[out['filesystem'],out['mount'],out['root']],issues=issues,findings=findings),state

def journal_filesystem(ctx,table):
    host=ctx.host;rows=[];findings=[];out={'ancestors':rows,'floor_bytes':FLOOR_BYTES,'five_session_need_bytes':FIVE_SESSION_NEED_BYTES}
    guarded(ctx,JOURNAL_ROOT);guarded(ctx,STATE_ROOT)
    with Held(host) as held:
        fd=held.keep(descend(host,JOURNAL_BASE,ctx.check,rows));deepest=JOURNAL_BASE;base=fd;parent=None
        docker=peek(ctx,base,'docker')
        chain={JOURNAL_PARENT:{'exists':False},JOURNAL_ROOT:{'exists':False},STATE_ROOT:{'exists':False}}
        for path,name in ((JOURNAL_PARENT,'c3po-bar'),(JOURNAL_ROOT,'journal')):
            info,opened=enter(ctx,fd,name)
            if info is None:break
            chain[path]={'exists':True,**shape(info),'root_root_private':root_private(info,'dir')}
            if not chain[path]['root_root_private']:
                findings.append('JOURNAL_PARENT_NOT_ROOT_0700' if path==JOURNAL_PARENT else 'JOURNAL_ROOT_NOT_ROOT_0700')
            if opened is None:break
            fd=held.keep(opened);deepest=path
            if path==JOURNAL_PARENT:
                parent=fd;info=peek(ctx,parent,'supervisor')
                if info is not None:
                    chain[STATE_ROOT]={'exists':True,**shape(info),'root_root_private':root_private(info,'dir')}
                    if not chain[STATE_ROOT]['root_root_private']:findings.append('STATE_ROOT_NOT_ROOT_0700')
        out.update(journal_parent=chain[JOURNAL_PARENT],journal_root=chain[JOURNAL_ROOT],state_root=chain[STATE_ROOT],statvfs_of=deepest)
        facts=attempt(lambda:filesystem(host,fd));out['filesystem']=facts;parts=[facts]
        if facts.get('status')=='COMPLETE':
            available=facts['bytes_available_to_non_root_f_bavail']
            out['mount']=holder(table,deepest,facts);parts.append(out['mount'])
            # device_differs_from_data_volume stays null until the data volume has been read (relate_journal).
            out.update(available_ge_floor=available>=FLOOR_BYTES,available_ge_five_session_need=available>=FIVE_SESSION_NEED_BYTES,
                       margin_over_five_session_need_bytes=available-FIVE_SESSION_NEED_BYTES,
                       device_differs_from_data_volume=None,
                       docker_root_on_the_same_device=None if docker is None else docker.st_dev==facts['device'])
            if available<FLOOR_BYTES:findings.append('BELOW_FLOOR')
            if available<FIVE_SESSION_NEED_BYTES:findings.append('BELOW_FIVE_SESSION_NEED')
            if facts['read_only']:findings.append('JOURNAL_FILESYSTEM_READ_ONLY')
        if deepest==JOURNAL_ROOT:
            session=re.compile(NAME_CLASSES['session_directory'])
            def classify(name,info):
                if name in ('epoch.json','maintenance.lock','producer.lock'):return [(name.replace('.','_'),None)]
                match=session.fullmatch(name)
                if match and stat.S_ISDIR(info.st_mode) and day_of(match.group(1)):return [('session_directory',match.group(1))]
                return [('other',None)]
            def listing():
                # Which sessions exist needs the whole listing: a capped one is a problem, and an unseen session is null.
                value,dates=census(ctx,fd,classify,live=True,cap_is_problem=True);found=dates.get('session_directory',set())
                value['sessions_of_this_epoch_present']={day:True if day in found else None if value['capped'] else False for day in SESSIONS}
                return value
            out['journal_listing']=attempt(listing);parts.append(out['journal_listing'])
    return finish(out,parts,findings=findings)

def relate_journal(section,device):
    """The journal is read before any docker command and the data volume after them: the one comparison between the
    two is made here, from two numbers already observed."""
    facts=section.get('filesystem')
    if type(facts) is not dict or facts.get('status')!='COMPLETE' or 'device_differs_from_data_volume' not in section:return
    section['device_differs_from_data_volume']=None if device is None else facts['device']!=device
    if section['device_differs_from_data_volume'] is False:
        section['findings']=sorted(set(section.get('findings') or [])|{'JOURNAL_DEVICE_EQUALS_DATA_DEVICE'})

def reader_tree(ctx,fd,findings,classify=None):
    """Shape, what uid 0 without capabilities may do, and the aggregates of one open reader-input directory. These
    directories are written and polled by running services: an access time moved by another reader is a fact here."""
    info=ctx.host.fstat(fd);facts,dates=census(ctx,fd,classify,live=True,cap_is_problem=True);may=access(info)
    facts.update(leaf(info),device=info.st_dev,access_as_uid0_without_capabilities=may,private=stat.S_IMODE(info.st_mode)&0o077==0)
    if not (may['read'] and may['search_or_execute']) or facts['counters'].get('uid0_nocap_unreadable'):findings.append('INPUT_UNREADABLE_UID0_NOCAP')
    if facts['counters'].get('private_not_uid0') or (facts['private'] and info.st_uid!=0):findings.append('PRIVATE_INPUT_NOT_UID0')
    return facts,dates

def data_root(ctx,shared,held,rows):
    need(shared.get('data_source') is not None,'DATA_SOURCE_UNAVAILABLE')
    guarded(ctx,shared['data_source'],tree=True)
    return held.keep(descend(ctx.host,shared['data_source'],ctx.check,rows))

def raw_spool(ctx,shared):
    host=ctx.host;findings=[];issues=[];components=[];out={'components':components,'below':'/'.join(RAW_PARTS)}
    session=re.compile(NAME_CLASSES['session_directory']);part=re.compile(NAME_CLASSES['raw_part'])
    with Held(host) as held:
        fd=data_root(ctx,shared,held,[])
        for label in RAW_PARTS:
            info,opened=enter(ctx,fd,label)
            if info is None:
                components.append({'label':label,'exists':False});findings.append('RAW_COMPONENT_MISSING')
                return finish(out,findings=findings)
            may=access(info);private=stat.S_IMODE(info.st_mode)&0o077==0
            components.append({'label':label,'exists':True,**leaf(info),'access_as_uid0_without_capabilities':may,'private':private})
            need(not stat.S_ISLNK(info.st_mode),'SYMLINK_COMPONENT');need(opened is not None,'COMPONENT_NOT_DIRECTORY')
            fd=held.keep(opened)
            # Every component is traversed by the reader: the design refusal holds for each of them, not only for the leaf.
            if not may['search_or_execute']:findings.append('INPUT_UNREADABLE_UID0_NOCAP')
            if private and info.st_uid!=0:findings.append('PRIVATE_INPUT_NOT_UID0')
            if stat.S_IMODE(info.st_mode)&0o022 and label==RAW_PARTS[-1]:findings.append('RAW_WRITABLE_BY_OTHERS')
        def classify(name,info):
            match=session.fullmatch(name)
            if match and stat.S_ISDIR(info.st_mode) and day_of(match.group(1)):return [('session',match.group(1))]
            return [('not_a_session',None)]
        facts,dates=reader_tree(ctx,fd,findings,classify);days=sorted(dates.get('session',set()))
        out['root']=facts;out['sessions']={'count':facts['classes'].get('session',0),'not_a_session_count':facts['classes'].get('not_a_session',0),
                                           'oldest_date':days[0] if days else None,'newest_date':days[-1] if days else None}
        if facts['counters'].get('group_other_writable'):findings.append('RAW_WRITABLE_BY_OTHERS')
        if facts['count']>READER_FILE_LIMIT:findings.append('RAW_ENTRY_LIMIT')
        sampled=[];out['sampled_newest_sessions']=sampled
        for day in reversed(days[-RAW_SESSION_SAMPLE:]):
            def sample(day=day):
                info,opened=enter(ctx,fd,'session_date='+day)
                if opened is None:return {'status':'COMPLETE','date':day,'vanished':True}
                with Held(host) as inner:
                    inner.keep(opened)
                    def parts(name,info):
                        return [('part',None)] if part.fullmatch(name) and stat.S_ISREG(info.st_mode) else [('not_a_part',None)]
                    value,_=reader_tree(ctx,opened,findings,parts)
                value['date']=day;value['parts_count']=value['classes'].get('part',0)
                value['not_a_part_count']=value['classes'].get('not_a_part',0)
                if stat.S_IMODE(info.st_mode)&0o022 or value['counters'].get('group_other_writable'):findings.append('RAW_WRITABLE_BY_OTHERS')
                if value['count']>READER_FILE_LIMIT:findings.append('RAW_ENTRY_LIMIT')
                return value
            item=attempt(sample);item.setdefault('date',day);sampled.append(item)
    return finish(out,[out['root']]+out['sampled_newest_sessions'],issues=issues,findings=findings)

def source_directory(ctx,shared):
    host=ctx.host;findings=[];candidates=[];day_file=re.compile(NAME_CLASSES['day_file'])
    with Held(host) as held:
        fd=data_root(ctx,shared,held,[])
        for index,name in enumerate(SOURCE_CANDIDATES):
            def one(name=name):
                with Held(host) as inner:
                    info,opened=enter(ctx,fd,name)
                    if info is None:
                        findings.append('SOURCE_DIRECTORY_ABSENT');return {'status':'COMPLETE','exists':False}
                    if opened is None:
                        findings.append('SOURCE_NOT_A_DIRECTORY');return {'status':'COMPLETE','exists':True,**leaf(info)}
                    inner.keep(opened);item,_=reader_tree(ctx,opened,findings);item['exists']=True
                    if not item['private']:findings.append('SOURCE_NOT_PRIVATE')
                    snapshot=peek(ctx,opened,'snapshot.json')
                    item['snapshot']=({'exists':True,**leaf(snapshot),'private':stat.S_IMODE(snapshot.st_mode)&0o077==0}
                                      if snapshot is not None else {'exists':False})
                    def tree(directory,label,classify=None):
                        info,sub=enter(ctx,directory,label)
                        if info is None:return {'status':'COMPLETE','exists':False},None,None
                        if sub is None:
                            findings.append('SOURCE_NOT_A_DIRECTORY');return {'status':'COMPLETE','exists':True,**leaf(info)},None,None
                        inner.keep(sub);value,dates=reader_tree(ctx,sub,findings,classify);value['exists']=True
                        if not value['private']:findings.append('SOURCE_NOT_PRIVATE')
                        return value,sub,dates
                    item['events'],_,_=tree(opened,'events')
                    if item['events'].get('count',0)>READER_FILE_LIMIT:findings.append('EVENT_FILE_LIMIT')
                    if item['events'].get('counters',{}).get('not_private'):findings.append('SOURCE_FILE_NOT_PRIVATE')
                    item['causal_list'],lists,_=tree(opened,'causal_list')
                    item['causal_epoch']={'status':'COMPLETE','exists':False}
                    if lists is not None:
                        def days(name,info):
                            match=day_file.fullmatch(name)
                            if match and stat.S_ISREG(info.st_mode) and day_of(match.group(1)):return [('day_file',match.group(1))]
                            return [('other',None)]
                        item['causal_epoch'],_,dates=tree(lists,EPOCH,days)
                        if dates is not None:
                            found=dates.get('day_file',set())
                            item['causal_epoch']['session_dates_present']={day:day in found for day in SESSIONS}
                            if item['causal_epoch']['counters'].get('not_private'):findings.append('SOURCE_FILE_NOT_PRIVATE')
                    item['status']=combined([{'status':item['status']},item['events'],item['causal_list'],item['causal_epoch']])
                    return item
            item=attempt(one);item['candidate_index']=index;candidates.append(item)
    return finish({'candidates':candidates,'epoch':EPOCH},candidates,findings=findings)

def release_directories(ctx,shared,names):
    host=ctx.host;findings=[];rows=[]
    if not names:return finish({'candidates':[],'candidate_count':0},findings=['NO_RELEASE_DIRECTORY_CANDIDATE_SIGNED'])
    with Held(host) as held:
        fd=data_root(ctx,shared,held,[])
        for index,name in enumerate(names):
            def one(name=name):
                info,opened=enter(ctx,fd,name)
                if info is None:return {'status':'COMPLETE','exists':False}
                if opened is None:
                    findings.append('RELEASE_CANDIDATE_NOT_A_DIRECTORY');return {'status':'COMPLETE','exists':True,**leaf(info)}
                with Held(host) as inner:
                    inner.keep(opened)
                    def classify(name,info):
                        return [('json_file',None)] if name.endswith('.json') and stat.S_ISREG(info.st_mode) else [('other',None)]
                    item,_=reader_tree(ctx,opened,findings,classify)
                item['exists']=True;item['json_file_count']=item['classes'].get('json_file',0)
                if item['counters'].get('not_private'):findings.append('RELEASE_FILE_NOT_PRIVATE')
                return item
            item=attempt(one);item['candidate_index']=index;rows.append(item)
    return finish({'candidates':rows,'candidate_count':len(names)},rows,findings=findings)

def capacity_candidates(ctx,shared,paths):
    host=ctx.host;findings=[];rows=[]
    if not paths:return finish({'candidates':[],'candidate_count':0},findings=['NO_CAPACITY_ROOT_CANDIDATE_SIGNED'])
    for index,path in enumerate(paths):
        def one(path=path):
            walked=[];item={'status':'COMPLETE','under_app_dir':below(path,APP_DIR),
                            'under_data_source':any(below(path,source) for source in DATA_SOURCES)}
            def ancestors():return [{key:value for key,value in row.items() if key!='path'} for row in walked]
            guarded(ctx,path)
            with Held(host) as held:
                try:fd=held.keep(descend(host,path,ctx.check,walked))
                except FileNotFoundError:
                    item.update(exists=False,absent_at_depth=len(walked),ancestors=ancestors());return item
                info=host.fstat(fd);root=host.fstat(held.keep(host.open('/',DIRECTORY|host.noatime())))
                def classify(name,info):return [('known_child' if name in CAPACITY_CHILDREN else 'other_child',None)]
                listing,_=census(ctx,fd,classify)
                item.update(exists=True,ancestors=ancestors(),**shape(info),root_root_private=root_private(info,'dir'),listing=listing,
                            device_equals_data_volume=None if shared.get('data_device') is None else info.st_dev==shared['data_device'],
                            device_equals_root_filesystem=info.st_dev==root.st_dev,children={})
                item['status']=listing['status']
                for name in CAPACITY_CHILDREN:
                    child=peek(ctx,fd,name)
                    item['children'][name]=({'exists':True,**shape(child),'root_root_private':root_private(child,'dir')}
                                            if child is not None else {'exists':False})
                if not item['root_root_private']:findings.append('CAPACITY_ROOT_NOT_ROOT_0700')
            if item['under_app_dir']:findings.append('CAPACITY_ROOT_UNDER_APP_DIR')
            if item['under_data_source']:findings.append('CAPACITY_ROOT_UNDER_DATA_VOLUME')
            return item
        item=attempt(one);item['candidate_index']=index;rows.append(item)
    return finish({'candidates':rows,'candidate_count':len(paths)},rows,findings=findings)

def host_layout(ctx):
    host=ctx.host;findings=[];paths={};day_file=re.compile(NAME_CLASSES['day_file'])
    for path,form,mode,counted in LAYOUT:
        def one(path=path,form=form,mode=mode,counted=counted):
            guarded(ctx,path);state,value=locate(host,path,ctx.check)
            if state=='absent':return {'status':'COMPLETE','exists':False,'absent_at':value}
            if state=='symlink':return {'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','at':value}
            item={'status':'COMPLETE','exists':True,**leaf(value)}
            if form is not None:
                item['as_documented']=item['type']==form and value.st_uid==0 and value.st_gid==0 and item['mode_octal']==mode
                if not item['as_documented']:findings.append('LAYOUT_NOT_AS_DOCUMENTED')
            else:findings.append('UNDOCUMENTED_PATH_PRESENT')
            if item['type']=='file':item['link_count']=value.st_nlink
            if path==TOKEN_PATH:item['size_within_1_4096']=1<=value.st_size<=4096
            if counted and item['type']=='dir':
                with Held(host) as held:
                    fd=held.keep(descend(host,path,ctx.check,[]))
                    def classify(name,info):
                        return [('day_file' if day_file.fullmatch(name) and stat.S_ISREG(info.st_mode) else 'other',None)]
                    listing,_=census(ctx,fd,classify if path==MANIFESTS_PATH else None)
                item['listing']=listing;item['empty']=listing['count']==0;item['status']=listing['status']
                if path==MANIFESTS_PATH and not item['empty']:findings.append('MANIFESTS_NOT_EMPTY')
            return item
        paths[path]=attempt(one)
    return finish({'paths':paths,'present':sorted(path for path,item in paths.items() if item.get('exists') is True),
                   'documented_owner':'root:root for every path'},paths.values(),findings=findings)

def properties(raw,keys):
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'PROPERTY_OUTPUT_INVALID')
    found={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=')
        need(separator=='=','PROPERTY_LINE_INVALID')
        if key in keys:
            need(key not in found and text(value,'[A-Za-z0-9_./:@+-]{0,128}'),'PROPERTY_VALUE_INVALID');found[key]=value
    return {key:found.get(key) for key in keys},sorted(set(keys)-set(found))

def systemd(ctx):
    """Runs before every docker command. The docker commands are opened here, and only on a complete answer that says
    ActiveState=active: with a stopped daemon, a client call to its endpoint can make the service manager start it."""
    findings=[];lists={'LoadState':LOAD_STATES,'ActiveState':ACTIVE_STATES,'UnitFileState':FILE_STATES,'SubState':SUB_STATES}
    def show(name,keys,unit):
        values,missing=properties(ctx.output(name),keys);issues=[]
        if missing:issues.append('PROPERTY_MISSING')
        if values.get('Id')!=unit:issues.append('UNIT_ID_MISMATCH')
        out={'status':'COMPLETE' if not issues else 'PARTIAL','issues':issues}
        for key in keys:
            if key=='Id':continue
            out[key]=token(values[key],lists[key])
            if out[key]=='OTHER':findings.append('UNIT_STATE_OUTSIDE_ALLOW_LIST')
        return out
    units={DOCKER_UNIT:attempt(lambda:show('docker_unit',('Id','ActiveState','SubState','UnitFileState'),DOCKER_UNIT))}
    seen=units[DOCKER_UNIT].get('status')=='COMPLETE'
    ctx.docker_block=(None if seen and units[DOCKER_UNIT].get('ActiveState')=='active' else
                      'DOCKER_SKIPPED_UNIT_NOT_ACTIVE' if seen else 'DOCKER_SKIPPED_UNIT_UNOBSERVED')
    for unit in UNITS:
        units[unit]=attempt(lambda unit=unit:show('unit:'+unit,('Id','LoadState','ActiveState','UnitFileState'),unit))
    if units[DOCKER_UNIT].get('ActiveState') not in (None,'active'):findings.append('DOCKER_UNIT_NOT_ACTIVE')
    return finish({'units':units,'systemctl_path':ctx.path('systemctl'),'docker_commands_allowed':ctx.docker_block is None,
                   'installed':sorted(unit for unit,item in units.items() if item.get('LoadState') not in (None,'not-found'))},
                  units.values(),findings=findings)

def aged(value,now):
    try:point=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (AttributeError,TypeError,ValueError):return None
    if point.tzinfo is None:return None
    return int(now-point.timestamp())
def sealed(report):
    """The repository's own seal: sha256 of the report without its seal member, sorted keys, compact, not ASCII-escaped."""
    try:body={key:value for key,value in report.items() if key!='report_sha256'}
    except AttributeError:return False
    try:raw=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    except (TypeError,ValueError):return False
    return sha(raw)==report.get('report_sha256')

def security_controller(ctx):
    host=ctx.host;findings=[];now=host.now()
    def stamped(info):return {**leaf(info),'mtime_epoch':seconds(info),'age_seconds':int(now-seconds(info))}
    def count(value):
        """A count taken from a report is emitted only inside a fixed range: anything else is a finding, never a number."""
        if type(value) is int and 0<=value<=REPORT_COUNT_LIMIT:return value
        if value is not None:findings.append('REPORT_COUNT_OUT_OF_RANGE')
        return None
    probes={label:attempt(lambda path=path:probe(ctx,path,stamped)) for label,path in sorted(SECURITY_PROBES.items())}
    def var_run():
        guarded(ctx,VAR_RUN);state,value=locate(host,VAR_RUN,ctx.check)
        if state!='present':return {'status':'COMPLETE','exists':False}
        item={'status':'COMPLETE','exists':True,'type':kind(value.st_mode),'resolves_to_run':None}
        if item['type']=='symlink':
            with Held(host) as held:
                fd=held.keep(descend(host,str(PurePosixPath(VAR_RUN).parent),ctx.check,[]))
                target=host.readlink(PurePosixPath(VAR_RUN).name,fd)
            item['resolves_to_run']=target in ('/run','../run','/run/','../run/')
        elif item['type']=='dir':
            # The controller names the flag below /var/run. Where that is a directory of its own, it is read there too.
            below_it=probe(ctx,VAR_RUN+'/'+PurePosixPath(REBOOT_REQUIRED).name,stamped)
            item['reboot_required_below_var_run']=below_it;item['status']=below_it['status']
        return item
    def policy():
        facts,raw=read_at(ctx,POLICY_DIR,POLICY_NAME,POLICY_LIMIT)
        if raw is None:return unread(facts,raw) or facts
        value=document(raw,POLICY_LIMIT,'POLICY_INVALID')
        facts.update(sha256=sha(raw),schema_known=value.get('schema')==POLICY_SCHEMA,automatic_merge=tri(value.get('automatic_merge')),
                     automatic_reboot=tri(value.get('automatic_reboot')),
                     other_key_count=len(set(value)-{'schema','automatic_merge','automatic_reboot'}))
        return facts
    def automation():
        facts,raw=read_at(ctx,SECURITY_DIR,AUTOMATION_REPORT,REPORT_LIMIT)
        if raw is None:return unread(facts,raw) or facts
        value=document(raw,REPORT_LIMIT,'REPORT_INVALID');errors=value.get('errors');deployed=value.get('deployed_sha')
        facts.update(seal_ok=sealed(value),age_seconds=aged(value.get('generated_at'),now),status_reported=token(value.get('status'),AUTOMATION_STATUS),
                     reboot_action=token(value.get('reboot_action'),REBOOT_ACTIONS),reboot_required=tri(value.get('reboot_required')),
                     automatic_reboot=tri(value.get('automatic_reboot')),healthy=tri(value.get('healthy')),
                     security_pending=count(value.get('security_pending')),
                     error_count=len(errors) if type(errors) is list else None,
                     open_alert_count=len(value['alerts']) if type(value.get('alerts')) is list else None,
                     deployed_sha=deployed if text(deployed,HEX40) else None,
                     deployed_equals_main=type(deployed) is str and deployed==value.get('main_sha'))
        return facts
    def host_report():
        facts,raw=read_at(ctx,SECURITY_DIR,HOST_REPORT,REPORT_LIMIT)
        if raw is None:return unread(facts,raw) or facts
        value=document(raw,REPORT_LIMIT,'REPORT_INVALID');updates=value.get('updates') if type(value.get('updates')) is dict else {}
        unattended=value.get('unattended_upgrades') if type(value.get('unattended_upgrades')) is dict else {}
        packages=value.get('reboot_packages')
        facts.update(seal_ok=sealed(value),age_seconds=aged(value.get('generated_at'),now),schema_known=value.get('schema')==HOST_REPORT_SCHEMA,
                     reboot_required=tri(value.get('reboot_required')),
                     reboot_package_count=len(packages) if type(packages) is list else None,
                     security_pending=count(updates.get('security_pending')),all_pending=count(updates.get('all_pending')),
                     healthcheck_configured=tri(unattended.get('healthcheck_configured')),
                     unattended_automatic_reboot=tri(unattended.get('automatic_reboot')))
        return facts
    def module(name):
        facts,raw=read_at(ctx,MODULE_DIR,name,MODULE_LIMIT)
        if raw is not None:facts.update(sha256=sha(raw),bytes=len(raw))
        return unread(facts,raw) or facts
    # The trial veto comes from the listing of the data volume, which is read after the docker commands: the three
    # members that depend on it stay null here and are filled in by relate_security().
    out={'probes':probes,'var_run':attempt(var_run),'policy':attempt(policy),'automation_report':attempt(automation),
         'host_report':attempt(host_report),'modules':{name:attempt(lambda name=name:module(name)) for name in MODULES},
         'controller_trial_veto':None,'automatic_reboot_held_by':None,'host_state_holds_automatic_reboot':None,
         'not_read':['hold text','package list','host security environment file','reboot state content','boot id','release files',
                     'the probe lock table','GitHub side state']}
    flag=probes['reboot_required'].get('exists')
    if out['var_run'].get('reboot_required_below_var_run',{}).get('exists'):flag=True
    out['reboot_pending']=flag
    out['reboot_flag_can_be_written']=probes['reboot_flag_writer'].get('exists')
    if probes['maintenance_hold'].get('exists'):findings.append('HOLD_PRESENT')
    if flag:findings.append('REBOOT_PENDING')
    if out['host_report'].get('reboot_required')=='true' and flag is False:findings.append('REBOOT_REPORTED_WITHOUT_FLAG')
    if probes['controller_reboot_marker'].get('exists') or probes['gate_reboot_marker'].get('exists'):findings.append('REBOOT_REQUEST_MARKER_PRESENT')
    if out['var_run'].get('resolves_to_run') is False or out['var_run'].get('type') not in (None,'symlink'):findings.append('VAR_RUN_IS_NOT_A_LINK_TO_RUN')
    for label in ('automation_report','host_report'):
        if out[label].get('seal_ok') is False:findings.append('REPORT_SEAL_MISMATCH')
    return finish(out,list(probes.values())+[out['var_run'],out['policy'],out['automation_report'],out['host_report']]
                  +list(out['modules'].values()),findings=findings)

def relate_security(section,veto):
    """Which observed host states hold an automatic reboot. A policy token is listed only when the policy content was
    read or the file is proved absent; a policy that could not be read is not taken for 'not true'."""
    if type(section.get('probes')) is not dict or type(section.get('policy')) is not dict:return
    policy=section['policy'];held=[];veto=veto or {}
    known=policy.get('status')=='COMPLETE' and (policy.get('exists') is False or policy.get('content_read') is True)
    if section['probes']['maintenance_hold'].get('exists'):held.append('EXPLICIT_HOLD')
    if known and policy.get('automatic_reboot')!='true':
        held.append('POLICY_AUTOMATIC_REBOOT_NOT_TRUE' if policy.get('exists') else 'POLICY_ABSENT')
    for key,label in (('by_pin','TRIAL_PIN'),('by_unrecognised_name','TRIAL_NAME_UNRECOGNISED'),('by_symlink','TRIAL_SYMLINK'),
                      ('by_current_or_future_date','TRIAL_DATE'),('controller_would_fail_on_a_date','TRIAL_GUARD_WOULD_RAISE')):
        if veto.get(key) is True:held.append(label)
    if veto.get('by_release_file') not in (None,'NONE'):held.append('TRIAL_RELEASE_FILE_'+veto['by_release_file'])
    section['controller_trial_veto']=veto or None;section['automatic_reboot_held_by']=held
    # 'Nothing holds it' is an answer only when the veto, the whole listing behind it and the policy were all observed.
    answer=True if held else None if veto.get('listing_capped') else False
    section['host_state_holds_automatic_reboot']=answer if veto and known else None
    if section.get('reboot_pending') and held:
        section['findings']=sorted(set(section.get('findings') or [])|{'REBOOT_PENDING_AND_HELD'})

def processes(ctx):
    findings=[]
    def one(label):
        code,raw=ctx.call('process:'+label)
        if code not in (0,1):raise CommandFailed('PGREP_FAILED',code)
        need(re.fullmatch(rb'[0-9]{1,6}\n',raw) is not None,'PGREP_OUTPUT_INVALID');count=int(raw.decode('ascii'))
        need((count>0)==(code==0),'PGREP_OUTPUT_INVALID')
        if count:findings.append('V2_PROCESS_RUNNING')
        return {'status':'COMPLETE','count':count}
    counts={label:attempt(lambda label=label:one(label)) for label,_ in PROCESS_PATTERNS}
    return finish({'counts':counts,'pgrep_path':ctx.path('pgrep'),
                   'basis':'pgrep -c -f: the count of processes whose command line matches; the lines stay inside pgrep'},
                  counts.values(),findings=findings)

def alert_channels(ctx):
    def present(info):return {'type':kind(info.st_mode)}
    probes={label:attempt(lambda path=path:probe(ctx,path,present)) for label,path in sorted(ALERT_PROBES.items())}
    clients=sorted(label for label in ('sendmail','mail','mailx','msmtp','postfix','exim4','ssmtp','curl') if probes[label].get('exists'))
    return finish({'probes':probes,'clients_present':clients,'forwarder_of_the_reader_failure_marker_defined_in_the_repository':False,
                   'basis':'presence only; no address, URL or configuration is read; that a notice reaches a person cannot be observed'},
                  probes.values())


def reason_codes(value,found):
    if type(value) is dict:
        if value.get('status') not in (None,'COMPLETE'):
            for code in [value.get('code')]+list(value.get('issues') or []):
                if text(code,'[A-Z][A-Z0-9_]{0,79}'):found.add(code)
        for item in value.values():reason_codes(item,found)
    elif type(value) is list:
        for item in value:reason_codes(item,found)

def degraded(value):
    """True when any part below carries a status that is not COMPLETE: such a section is never reported COMPLETE."""
    if type(value) is dict:
        return value.get('status') not in (None,'COMPLETE') or any(degraded(item) for item in value.values())
    return type(value) is list and any(degraded(item) for item in value)

def finding_codes(value,found):
    if type(value) is dict:
        if type(value.get('findings')) is list:
            for code in value['findings']:
                if text(code,CODE):found.add(code)
        for item in value.values():finding_codes(item,found)
    elif type(value) is list:
        for item in value:finding_codes(item,found)

def validate_candidates(value):
    need(type(value) is dict and set(value)=={'release_directories','capacity_roots'},'CANDIDATES_INVALID')
    names,roots=value['release_directories'],value['capacity_roots']
    need(type(names) is list and len(names)<=MAX_RELEASE_CANDIDATES and all(text(name,ENTRY) and name not in ('.','..') for name in names)
         and len(set(names))==len(names),'CANDIDATES_INVALID')
    need(type(roots) is list and len(roots)<=MAX_CAPACITY_CANDIDATES and all(type(root) is str and data_path(root) for root in roots)
         and len(set(roots))==len(roots),'CANDIDATES_INVALID')

def validate_collection(collection):
    need(type(collection) is dict and set(collection)=={'schema','status','phase','scope','window','host_binding_sha256','max_seconds',
                                                         'candidates'},'COLLECTION_KEYS')
    need(collection['schema']==COLLECTION_SCHEMA and collection['status']=='BOUND','COLLECTION_UNBOUND')
    need(collection['phase']==PHASE,'PHASE_INVALID')
    need(type(collection['max_seconds']) is int and collection['max_seconds']==MAX_SECONDS,'LIMITS_INVALID')
    need(text(collection['host_binding_sha256'],HEX64) and collection['host_binding_sha256']!='0'*64,'HOST_UNBOUND')
    need(type(collection['scope']) is dict and canonical(collection['scope'])==canonical(SCOPE),'SCOPE_MISMATCH')
    need(type(collection['window']) is dict and set(collection['window'])=={'not_before','expires_at'},'COLLECTION_WINDOW')
    validate_candidates(collection['candidates'])

def collect(request,gate,host=None):
    # All shape validation precedes the first gate call, and that first call is outside every handler:
    # a refusal or a dry-run gate stops here before anything is observed.
    validate_collection(request)
    ctx=Context(host if host is not None else Native(),gate)
    ctx.check()
    releases=list(request['candidates']['release_directories']);roots=list(request['candidates']['capacity_roots'])
    sections={};shared={'observed':False,'rows':[],'raw':{},'per':{},'carriers':[],'others':[],'incomplete':True,'unknown':None,
                        'data_source':None,'data_device':None}
    production={'status':'UNAVAILABLE'}
    def run(name,action):
        try:
            ctx.check();section=action()
            if section.get('status')=='COMPLETE' and degraded(section):section['status']='PARTIAL'
            sections[name]=section
        except Exception as error:sections[name]=safe(error)
    def observed_containers():
        section,state=containers(ctx,roots);shared.update(state);return section
    def observed_images():
        section,tag=images(ctx,shared);production.clear();production.update(tag);return section
    def observed_volume():
        section,state=data_volume(ctx,shared,table);shared.update(data_source=state['source'],data_device=state['device'],veto=state.get('veto'))
        return section
    def late(name,action):
        # A derivation from values already observed. It cannot observe anything; if it fails the section says so.
        section=sections.get(name)
        try:
            if type(section) is dict:action(section)
        except Exception:
            section['status']='PARTIAL' if section.get('status')=='COMPLETE' else section.get('status')
            section['issues']=sorted(set(section.get('issues') or [])|{'DERIVATION_FAILED'})
    actor=attempt(lambda:dict(zip(('uid','gid'),ctx.host.identity())))
    table=attempt(lambda:mount_table(ctx));guard={'applied':False,'autofs_rows':None,'armed_points':None}
    if type(table) is list:
        count,ctx.autofs=automounts(table);guard={'applied':True,'autofs_rows':count,'armed_points':len(ctx.autofs)}
    # 1. What needs no external tool at all: nothing a slow daemon does can take these away.
    run('runtime',lambda:runtime(ctx))
    run('journal_filesystem',lambda:journal_filesystem(ctx,table))
    run('host_layout',lambda:host_layout(ctx))
    run('security_controller',lambda:security_controller(ctx))
    run('alert_channels',lambda:alert_channels(ctx))
    # 2. systemctl and pgrep, both inside SYSTEM_TOOLS_SECONDS. The answer about docker.service, the first unit asked,
    # decides whether any docker command may start.
    run('systemd',lambda:systemd(ctx))
    run('processes',lambda:processes(ctx))
    # 3. The docker commands, all of them inside DOCKER_SECONDS.
    run('docker_daemon',lambda:docker_daemon(ctx))
    run('containers',observed_containers)
    run('worker',lambda:worker(shared,roots))
    run('worker_environment',lambda:worker_environment(ctx,shared))
    run('network',lambda:network(ctx,shared))
    run('images',observed_images)
    run('deploy_version',lambda:deploy_version(ctx,shared,production))
    # 4. The data volume, whose source is the mount the containers showed, and the trees below it.
    run('data_volume',observed_volume)
    run('raw_spool',lambda:raw_spool(ctx,shared))
    run('source_directory',lambda:source_directory(ctx,shared))
    run('release_directories',lambda:release_directories(ctx,shared,releases))
    run('capacity_candidates',lambda:capacity_candidates(ctx,shared,roots))
    # 5. Two derivations that join a section of step 1 with the data volume.
    late('journal_filesystem',lambda section:relate_journal(section,shared.get('data_device')))
    late('security_controller',lambda section:relate_security(section,shared.get('veto')))
    problems=[];findings=[];expired=False
    for name in sorted(sections):
        if sections[name].get('status')!='COMPLETE':
            found=set();reason_codes(sections[name],found);expired=expired or bool(found&set(EXPIRED))
            problems+=[name+':'+code for code in sorted(found) or ['INCOMPLETE']]
        found=set();finding_codes(sections[name],found);findings+=[name+':'+code for code in sorted(found)]
    try:ctx.check()
    except Refused:expired=True
    status='PARTIAL_OR_WINDOW_EXPIRED' if expired else 'OBSERVED_COMPLETE' if not problems else 'PARTIAL_OBSERVED'
    return {'schema':OBSERVATION_SCHEMA,'status':status,'actor':actor,'host_binding_sha256':request['host_binding_sha256'],
            'scope_sha256':SCOPE_SHA256,'candidate_counts':{'release_directories':len(releases),'capacity_roots':len(roots)},
            'automount_guard':guard,
            'sections':sections,'problems':problems[:MAX_PROBLEMS],'problems_truncated':len(problems)>MAX_PROBLEMS,
            'findings':findings[:MAX_FINDINGS],'findings_truncated':len(findings)>MAX_FINDINGS,
            'findings_do_not_change_the_status':True,'commands_started':ctx.calls,
            'writes':0,'container_commands':0,'container_environment_values_received':0,'secret_bytes_read':0,
            'application_imports':0,'entry_names_emitted':0,'file_contents_read':FILE_CONTENTS_READ,
            'histogram_columns':HISTOGRAM_COLUMNS,'counters_listed_only_when_not_zero':COUNTERS,
            'ready':False,'installation_authorized':False,'activation_authorized':False}


# Authenticated stdin API. These primitives are also consumed by the explicitly
# adapted once dispatcher; this operation accepts no GO of an earlier operation.
@dataclass(frozen=True)
class Pins:
    payload:str
    request:str
    authority:str
    go:str
class Gate:
    def __init__(self,start,end,clock,monotonic):
        self.start,self.end,self.clock,self.monotonic=start,end,clock,monotonic
        self.wall,self.mono=clock(),monotonic();self.deadline=self.mono+MAX_SECONDS
        need(start<=self.wall<end,'OUTSIDE_GO_WINDOW')
    def __call__(self):
        wall,mono=self.clock(),self.monotonic()
        need(wall>=self.wall and mono>=self.mono,'CLOCK_REVERSED')
        self.wall,self.mono=wall,mono
        need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')
        return min((self.end-wall).total_seconds(),self.deadline-mono)

def authenticate(request_bytes,authority_bytes,go_bytes,*,pins,payload_bytes,
                 clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
                 executor_uid=os.geteuid):
    for name,data in [('request',request_bytes),('authority',authority_bytes),('go',go_bytes),('payload',payload_bytes)]:
        pin=getattr(pins,name)
        need(type(pin) is str and re.fullmatch(HEX64,pin) and pin!='0'*64 and type(data) is bytes and sha(data)==pin,'PIN_MISMATCH')
    request,authority,go=map(decode,(request_bytes,authority_bytes,go_bytes))
    need(request.get('schema')==REQUEST_SCHEMA and request.get('status')=='BOUND'
         and request.get('operation')==OPERATION and request.get('phase')==PHASE
         and request.get('dates')==DATES and request.get('scope_sha256')==SCOPE_SHA256
         and request.get('payload_sha256')==pins.payload and request.get('executor_uid')==0
         and type(request.get('executor_uid')) is int and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')
    need(request.get('max_seconds')==MAX_SECONDS and request.get('writes_allowed') is False
         and request.get('activation_allowed') is False,'REQUEST_SCOPE')
    need(authority.get('schema')==AUTHORITY_SCHEMA
         and authority.get('operation')==OPERATION and authority.get('status')=='SIGNED'
         and authority.get('decision')=='APPROVED' and authority.get('execution_authorized') is True
         and authority.get('request_sha256')==pins.request and authority.get('writes_allowed') is False
         and authority.get('activation_allowed') is False,'AUTHORITY_UNBOUND')
    need(go.get('schema')==GO_SCHEMA and go.get('status')=='SIGNED'
         and go.get('action')=='GO' and go.get('phase')==PHASE
         and go.get('operation')==OPERATION and go.get('execution_authorized') is True
         and go.get('writes_allowed') is False and go.get('activation_allowed') is False
         and go.get('request_sha256')==pins.request and go.get('authority_sha256')==pins.authority
         and go.get('payload_sha256')==pins.payload,'GO_UNBOUND')
    need(type(go.get('owner')) is str and go['owner'] not in ('','UNBOUND')
         and go['owner']==authority.get('owner'),'OWNER_UNBOUND')
    host=request.get('host_binding_sha256')
    need(type(host) is str and re.fullmatch(HEX64,host) and host!='0'*64
         and host==authority.get('host_binding_sha256')==go.get('host_binding_sha256'),'HOST_BINDING')
    starts=[instant(d.get('not_before')) for d in (request,authority,go)]
    ends=[instant(d.get('not_after')) for d in (request,authority,go)]
    days={point.date().isoformat() for point in starts+ends}
    need(len(days)==1 and days<=set(DATES),'DATE_WINDOW_MISMATCH')
    gate=Gate(max(starts),min(ends),clock,monotonic);gate()
    collection=request.get('collection')
    need(type(collection) is dict and collection.get('host_binding_sha256')==host,'COLLECTION_BINDING')
    validate_collection(collection)
    need(instant(collection['window']['not_before'])==starts[0]
         and instant(collection['window']['expires_at'])==ends[0],'COLLECTION_WINDOW')
    return collection,gate

def _strip(value,key):
    if type(value) is dict:
        if key in value:value[key]=[]
        for item in value.values():_strip(item,key)
    elif type(value) is list:
        for item in value:_strip(item,key)
def _drop_histograms(observation):_strip(observation['sections'],'histogram')
def _drop_mounts(observation):
    for row in observation['sections']['containers']['rows']:
        if type(row.get('mounts')) is list:row['mounts']=[];row['mounts_dropped_for_size']=True
def _reduce_rows(observation):
    keep=('status','service','oneoff','container_id','image_id','state','running','code')
    section=observation['sections']['containers']
    section['rows']=[{key:row[key] for key in keep if key in row} for row in section['rows']]
    section['rows_reduced_for_size']=True
def _reduce_sections(observation):
    observation['sections']={name:{'status':section.get('status'),'reduced_for_size':True}
                             for name,section in observation['sections'].items()}
REDUCTIONS=[('HISTOGRAMS_DROPPED',_drop_histograms),('MOUNTS_DROPPED',_drop_mounts),
            ('CONTAINER_ROWS_REDUCED',_reduce_rows),('SECTIONS_REDUCED',_reduce_sections)]

def seal(receipt):
    """Fit the dispatcher's 64 KiB decode limit by explicit flagged reduction, then hash. Never raises."""
    def size():return len(canonical(receipt))+SEAL_OVERHEAD
    try:
        applied=[];receipt['observation']['size_reductions']=applied
        for name,step in REDUCTIONS:
            if size()<=RECEIPT_LIMIT:break
            applied.append(name);receipt['status']=PARTIAL_STATUS
            if receipt['observation'].get('status')=='OBSERVED_COMPLETE':receipt['observation']['status']='PARTIAL_OBSERVED'
            try:step(receipt['observation'])
            except Exception:applied.append(name+'_FAILED')
        need(size()<=RECEIPT_LIMIT,'RECEIPT_LIMIT')
    except Exception:
        receipt['status']=PARTIAL_STATUS
        receipt['observation']={'schema':OBSERVATION_SCHEMA,'status':'PARTIAL_OBSERVED','code':'RECEIPT_REDUCED_TO_MINIMUM',
                                'sections':{},'problems':['receipt:RECEIPT_REDUCED_TO_MINIMUM'],
                                'size_reductions':['RECEIPT_REDUCED_TO_MINIMUM']}
    receipt['metadata_sha256']=sha(canonical(receipt));return receipt

def observe(request_bytes,authority_bytes,go_bytes,*,pins,payload_bytes,
            clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
            executor_uid=os.geteuid,collector=collect):
    collection,gate=authenticate(request_bytes,authority_bytes,go_bytes,pins=pins,payload_bytes=payload_bytes,
                                clock=clock,monotonic=monotonic,executor_uid=executor_uid)
    host=collection['host_binding_sha256']
    # The host identity itself comes from the independently reviewed pinned SSH
    # transport. The hash here is its signed reference, not a new observation.
    begun,mark=clock(),monotonic()
    try:observed=collector(collection,gate)
    except Refused:raise
    except Exception:observed=None
    if type(observed) is not dict or type(observed.get('sections')) is not dict:
        observed={'schema':OBSERVATION_SCHEMA,'status':'PARTIAL_OBSERVED','code':'COLLECTOR_FAILED','sections':{},
                  'problems':['collector:COLLECTOR_FAILED']}
    try:
        ended,elapsed=clock(),monotonic()-mark
        need(ended>=begun and elapsed>=0,'CLOCK_REVERSED')
        observed['sections']['clock']={'status':'COMPLETE','utc_start':begun.isoformat(),'utc_end':ended.isoformat(),
                                       'monotonic_elapsed_ms':int(elapsed*1000)}
    except Exception as error:observed['sections']['clock']=safe(error)
    try:gate()
    except Refused:observed['status']='PARTIAL_OR_WINDOW_EXPIRED'
    if observed['sections']['clock'].get('status')!='COMPLETE' and observed.get('status')=='OBSERVED_COMPLETE':
        observed['status']='PARTIAL_OBSERVED'
    partial=observed.get('status')!='OBSERVED_COMPLETE'
    receipt={'schema':RECEIPT_SCHEMA,
             'status':PARTIAL_STATUS if partial else COMPLETE_STATUS,
             'request_sha256':pins.request,'authority_sha256':pins.authority,'go_sha256':pins.go,
             'payload_sha256':pins.payload,'host_binding_sha256':host,'observed_at':begun.isoformat(),
             'observation':observed,'source_mutation':False,'installation_authorized':False,
             'activation_authorized':False,'ready':False,'w1_is_not_readiness':True}
    return seal(receipt)

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
