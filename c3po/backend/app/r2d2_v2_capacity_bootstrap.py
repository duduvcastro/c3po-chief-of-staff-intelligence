"""Offline-configured capacity startup. All authority and pins must be supplied."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from .r2d2_v2_capacity_anchored import AnchoredRoot,need
from .r2d2_v2_document_authority import DocumentAuthority
from .r2d2_v2_document_format import PinnedVetoReader,RenewableVetoReader
from .r2d2_v2_calendar import ShadowCalendar,NEW_YORK
from .r2d2_v2_epoch_assembler import is_sha,validate_identity
from .r2d2_v2_capacity_bound import calendar_pin
from .r2d2_v2_earnings_package import implementation_package_sha


class ConfigAuthority(DocumentAuthority):
    def __init__(self,config):
        self.config=config
        super().__init__(root=config.roots['documents'],pins=config.body['document_pins'],revocation_reader=config.veto,restore_revocation_reader=config.restore_veto if config.veto_mode=='CONTINUOUS' else None)
        self.capacity_veto_mode=config.veto_mode

    def record(self,label):
        self.config.verify()
        return super().record(label)

    def verify_binding(self,document,now):
        try:
            self.config.verify()
            need(document['epoch']==self.config.body['identity']['epoch'],'CAPACITY_CONFIG_EPOCH')
            return super().verify_binding(document,now)
        except Exception:return False


class CapacityConfig:
    def __init__(self,settings,*,clock=None):
        self.roots={};self.config_root=None
        self.clock=clock or (lambda:datetime.now(timezone.utc));self.calendar=ShadowCalendar()
        try:
            path=Path(getattr(settings,'r2d2_v2_capacity_config_file',''))
            self.sha=getattr(settings,'r2d2_v2_capacity_config_sha','')
            need(path.is_absolute() and is_sha(self.sha),'CAPACITY_CONFIG_UNBOUND')
            self.config_root=AnchoredRoot(path.parent);self.name=path.name
            raw=self.config_root.read(self.name)
            need(hashlib.sha256(raw).hexdigest()==self.sha,'CAPACITY_CONFIG_HASH')
            def pairs(items):
                result={}
                for key,value in items:need(key not in result,'CAPACITY_CONFIG_DUPLICATE');result[key]=value
                return result
            self.body=json.loads(raw,object_pairs_hook=pairs)
            need(type(self.body) is dict,'CAPACITY_CONFIG_FIELDS')
            extra={'r2d2_v2_capacity_veto_mode'} if self.body.get('schema')=='R2D2_CAPACITY_BOOTSTRAP_V3' else set()
            need(set(self.body)=={'schema','identity','calendar_pin_sha','release_sha','package_sha','roots','document_pins','veto_views','restore_revocation'}|extra,'CAPACITY_CONFIG_FIELDS')
            b=self.body
            need(b['schema'] in {'R2D2_CAPACITY_BOOTSTRAP_V2','R2D2_CAPACITY_BOOTSTRAP_V3'},'CAPACITY_CONFIG_SCHEMA')
            self.veto_mode=b.get('r2d2_v2_capacity_veto_mode','CONTINUOUS')
            need(self.veto_mode in {'CONTINUOUS','DISPATCH_AND_DERIVATION_ONLY'} and self.veto_mode==getattr(settings,'r2d2_v2_capacity_veto_mode','DISPATCH_AND_DERIVATION_ONLY'),'CAPACITY_VETO_MODE')
            validate_identity(b['identity'],b['identity']['first_session'],self.calendar)
            need(b['calendar_pin_sha']==calendar_pin(self.calendar,b['identity']),'CAPACITY_CONFIG_CALENDAR')
            need(is_sha(b['release_sha']) and b['release_sha']==settings.r2d2_v2_shadow_release_sha,'CAPACITY_CONFIG_RELEASE')
            need(b['package_sha']==implementation_package_sha(),'CAPACITY_CONFIG_PACKAGE')
            need(type(b['roots']) is dict and set(b['roots'])=={'documents','payload','go'},'CAPACITY_CONFIG_ROOTS')
            for key,value in b['roots'].items():
                need(type(value) is dict and set(value)=={'path','identity'} and type(value['path']) is str and Path(value['path']).is_absolute() and is_sha(value['identity']),'CAPACITY_CONFIG_ROOT_PIN')
                self.roots[key]=AnchoredRoot(value['path'],expected_identity=value['identity'])
            need(type(b['document_pins']) is dict and {'CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE','B_DUDU','TEMPLATE'}<=set(b['document_pins']),'CAPACITY_CONFIG_DOCUMENT_PINS')
            for pin in b['document_pins'].values():self.check_pin(pin)
            need(type(b['veto_views']) is dict and set(b['veto_views'])<=set(b['identity']['authorized_sessions']) and b['veto_views'],'CAPACITY_CONFIG_VETO_VIEWS')
            for pin in b['veto_views'].values():self.check_pin(pin)
            channel=b['restore_revocation']
            if self.veto_mode=='DISPATCH_AND_DERIVATION_ONLY':
                need(channel is None,'CAPACITY_RESTORE_CHANNEL_DISABLED')
            else:
                need(type(channel) is dict and set(channel)=={'root','pointer_file'},'CAPACITY_RESTORE_CHANNEL')
                root=channel['root']
                need(type(root) is dict and set(root)=={'path','identity'} and type(root['path']) is str
                     and Path(root['path']).is_absolute() and is_sha(root['identity']),'CAPACITY_RESTORE_ROOT_PIN')
                name=channel['pointer_file']
                need(type(name) is str and name not in {'','.','..'} and '/' not in name,'CAPACITY_RESTORE_POINTER_FILE')
                self.roots['restore_revocation']=AnchoredRoot(root['path'],expected_identity=root['identity'])
            self.authority=ConfigAuthority(self)
        except BaseException:
            self.close();raise

    @staticmethod
    def check_pin(pin):
        need(type(pin) is dict and set(pin)=={'file','sha256'} and type(pin['file']) is str and pin['file'] not in {'','.','..'} and '/' not in pin['file'] and is_sha(pin['sha256']),'CAPACITY_CONFIG_PIN')

    def verify(self):
        need(hashlib.sha256(self.config_root.read(self.name)).hexdigest()==self.sha,'CAPACITY_CONFIG_CHANGED')
        for root in self.roots.values():root.verify()

    def release(self,release):
        self.verify();identity=self.body['identity']
        need(release.epoch==identity['epoch'] and release.first_session.isoformat()==identity['first_session']
             and release.receipt_sha==self.body['release_sha'] and release.implementation_package_sha==self.body['package_sha'],'CAPACITY_CONFIG_RELEASE')

    def veto(self,now):
        self.verify();day=now.astimezone(NEW_YORK).date().isoformat()
        need(day in self.body['veto_views'],'CAPACITY_VETO_DAY_UNBOUND')
        return PinnedVetoReader(self.roots['documents'],epoch=self.body['identity']['epoch'],day=day,
            order_sha=self.authority.record('ACT_B')['order_sha'],**self.body['veto_views'][day])(now)

    def restore_pin(self,now):
        # Mutable pointer is an explicitly authorized private evidence channel, not
        # an implicit fetch or a replacement for the immutable GO dispatch snapshot.
        self.verify();pointer=self.roots['restore_revocation'].json(self.body['restore_revocation']['pointer_file'])
        day=now.astimezone(NEW_YORK).date().isoformat()
        need(type(pointer) is dict and set(pointer)=={'schema','epoch','day','order_sha','file','sha256'},'RESTORE_REVOCATION_POINTER')
        need(pointer['schema']=='R2D2_RESTORE_REVOCATION_POINTER_V1' and pointer['epoch']==self.body['identity']['epoch']
             and pointer['day']==day and day in self.body['identity']['authorized_sessions']
             and pointer['order_sha']==self.authority.record('ACT_B')['order_sha'],'RESTORE_REVOCATION_SCOPE')
        pin={k:pointer[k] for k in ('file','sha256')};self.check_pin(pin)
        return pin

    def restore_veto(self,now):
        day=now.astimezone(NEW_YORK).date().isoformat()
        return RenewableVetoReader(self.roots['restore_revocation'],pin_provider=self.restore_pin,
            epoch=self.body['identity']['epoch'],day=day,order_sha=self.authority.record('ACT_B')['order_sha'])(now)

    def collector_config(self,release,store):
        self.release(release)
        def binding_reader(day):
            self.verify();saved=store.read(release.epoch)
            if saved is None:return None
            state=saved['state'];session=state.get('sessions',{}).get(day,{})
            return session.get('capacity_binding') or state.get('daily_capacity',{}).get(day)
        return {'payload_root':self.body['roots']['payload']['path'],'go_root':self.body['roots']['go']['path'],
                'authority':self.authority,'clock':self.clock,'binding_reader':binding_reader,'epoch':release.epoch}

    def planner(self,saved,release,policy,now):
        from .r2d2_v2_capacity_live import capacity_live_plan
        try:
            self.release(release)
            return capacity_live_plan(saved,release,policy,now,calendar=self.calendar,authority=self.authority)
        except Exception:
            from .r2d2_v2_live_group import plan_live_group
            return {**plan_live_group(saved,release,capacity=550),'capacity_plan_sha':None,'capacity_mode':'OPEN_ONLY_FALLBACK'}

    def close(self):
        for root in self.roots.values():root.close()
        if self.config_root is not None:self.config_root.close()


def load_capacity_planner(settings):
    return CapacityConfig(settings).planner
