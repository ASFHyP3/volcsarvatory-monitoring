def test_hyp3_volcsarvatory_monitoring(script_runner):
    ret = script_runner.run(['python', '-m', 'hyp3_volcsarvatory_monitoring', '-h'])
    assert ret.success
