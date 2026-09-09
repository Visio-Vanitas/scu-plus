"""Validate provisioning profiles and prepare manual App Store export."""
import datetime, os, pathlib, plistlib, subprocess
root=pathlib.Path(os.environ['RUNNER_TEMP'])
team=os.environ['APPLE_TEAM_ID']
base=os.environ['SAFARI_BUNDLE_ID']
profiles={}
for filename, bundle in [('app',base),('extension',base+'.Extension')]:
    path=root/'ios-signing'/f'{filename}.mobileprovision'
    data=plistlib.loads(subprocess.check_output(['security','cms','-D','-i',str(path)]))
    assert data['TeamIdentifier']==[team], 'Profile team mismatch'
    assert data['ExpirationDate'] > datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None), 'Expired profile'
    assert not data.get('ProvisionedDevices') and not data.get('ProvisionsAllDevices'), 'Expected App Store profile'
    ent=data['Entitlements']
    assert ent['application-identifier']==team+'.'+bundle, 'Profile bundle ID mismatch'
    assert not ent.get('get-task-allow'), 'Development profile cannot be distributed'
    profiles[bundle]=data['UUID']
    dest=pathlib.Path.home()/'Library/MobileDevice/Provisioning Profiles'/f'{data["UUID"]}.mobileprovision'
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(path.read_bytes())
options={'method':'app-store-connect','destination':'export','teamID':team,'signingStyle':'manual',
         'signingCertificate':'Apple Distribution','provisioningProfiles':profiles,
         'manageAppVersionAndBuildNumber':False,'uploadSymbols':True}
(root/'ios-export-options.plist').write_bytes(plistlib.dumps(options))
