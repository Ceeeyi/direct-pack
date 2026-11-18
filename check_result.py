from pathlib import Path
import argparse,json
import solver,runner
from audit import audit

def main():
    ap=argparse.ArgumentParser();ap.add_argument('config');ap.add_argument('state');args=ap.parse_args()
    c=json.loads(Path(args.config).read_text(encoding='utf-8'));s=runner.load(args.state)
    if s['context']!=runner.context(c):raise ValueError('result dependencies do not match current input/code')
    if s['best'] is None:
        print(json.dumps(dict(valid=False,stop=s['stop'],reason='no complete verified candidate'),ensure_ascii=False));return 2
    r=audit(c,s['best']['bins'])
    if r!=s['best']['audit']:raise ValueError('stored audit does not match independent recalculation')
    print(json.dumps(dict(valid=r['valid'],stage=r['stage'],boxes=r['n'],lower=s['lower'],
                         business_digest=solver.digest(s['best']),front_mean=r['front_mean'],overall_mean=r['overall_mean'],
                         height='not_verified' if not c['parameters']['height_check'] else 'checked'),ensure_ascii=False))
    return 0 if r['valid'] else 2
if __name__=='__main__':raise SystemExit(main())
