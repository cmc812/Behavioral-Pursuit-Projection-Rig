try
    Bpod;
catch
end

global BpodSystem

RPValveTimes = GetValveTimes(10, 1)

try
    eventNameList = BpodSystem.StateMachineInfo.EventNames;
catch
    eventNameList = {};
    warning('Could not read EventNames from BpodSystem — events will log as indices.');
end

softcodeMap = containers.Map();
softcodeMap('TrialStart') = 12;
softcodeMap('WaitForPoke') = 2;
softcodeMap('Success') = 11;

% --- CONFIG ---
% Path where Bonsai writes the session name before sending SoftCode0
sessionInfoPath = 'C:/BpodExchange/next_session.txt';
% Base directory for Bpod CSV logs
csvOutputDir = 'C:/BpodExchange/logs';
if ~exist(csvOutputDir, 'dir'), mkdir(csvOutputDir); end

% --- Start with no CSV open ---
fid = -1;
csvPath = '';
trialNum = 0;
sessionWallAnchor = [];
sessionBpodAnchor = [];

try
    while true
        trialNum = trialNum + 1;

        sma = NewStateMachine();

        sma = AddState(sma, 'Name', 'TrialStart', ...
            'Timer', 0, ...
            'StateChangeConditions', {'APP_SoftCode2', 'WaitForPoke', ...
            'APP_SoftCode4', 'WaitForPoke_Fail', ...
            'APP_SoftCode0', 'SessionStart', ...
            'APP_SoftCode10', 'TrialEnd', ...
            'APP_SoftCode1', 'SessionEnd'}, ...
            'OutputActions', {'PWM1', 255, 'APP_SoftCode', 12});

        sma = AddState(sma, 'Name', 'SessionStart', ...
            'Timer', 0, ...
            'StateChangeConditions', {'Tup', 'TrialStart'}, ...
            'OutputActions', {'PWM1', 255, 'BNC1', 1});

        sma = AddState(sma, 'Name', 'WaitForPoke', ...
            'Timer', 0, ...
            'StateChangeConditions', {'Port1In', 'Success', ...
            'APP_SoftCode10', 'TrialEnd'}, ...
            'OutputActions', {'PWM1', 255, 'APP_SoftCode', 2});

        sma = AddState(sma, 'Name', 'WaitForPoke_Fail', ...
            'Timer', 5, ...
            'StateChangeConditions', {'Port1In', 'TrialEnd', ...
            'APP_SoftCode10', 'TrialEnd'}, ...
            'OutputActions', {'PWM1', 255});

        sma = AddState(sma, 'Name', 'Success', ...
            'Timer', RPValveTimes(1), ...
            'StateChangeConditions', {'Tup', 'TrialEnd'}, ...
            'OutputActions', {'PWM1', 255, 'ValveState', 1, 'APP_SoftCode', 11, 'BNC2', 1});

        sma = AddState(sma, 'Name', 'TrialEnd', ...
            'Timer', 1, ...
            'StateChangeConditions', {'Tup', '>exit'}, ...
            'OutputActions', {'PWM1', 255, 'BNC1', 1});

        sma = AddState(sma, 'Name', 'SessionEnd', ...
            'Timer', 0, ...
            'StateChangeConditions', {'Tup', '>exit'}, ...
            'OutputActions', {});

        SendStateMachine(sma);
        disp(['Running trial ' num2str(trialNum) '...'])
        rawEvents = RunStateMachine;

        if isempty(rawEvents) || ~isstruct(rawEvents)
            disp('State machine returned empty — stopping.')
            break
        end
        if BpodSystem.Status.BeingUsed == 0
            disp('Bpod stop detected — stopping.')
            break
        end

        trialT0 = rawEvents.TrialStartTimestamp;
        if isempty(sessionWallAnchor)
            sessionWallAnchor = datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSSSSSxxx');
            sessionBpodAnchor = trialT0;
        end

        % --- Detect which states were visited this trial ---
        stateIndices = rawEvents.States;
        try stateNames = BpodSystem.StateMatrix.StateNames; catch, stateNames = sma.StateNames; end

        hitSessionStart = any(stateIndices == find(strcmp(stateNames, 'SessionStart')));
        hitSessionEnd   = any(stateIndices == find(strcmp(stateNames, 'SessionEnd')));

        % =============================================
        % SESSION START — read Bonsai's file, open CSV
        % =============================================
        if hitSessionStart
            % Close old CSV if one was open
            if fid > 0
                fclose(fid);
                fprintf('Previous session saved to %s\n', csvPath);
            end

            % Read full CSV path from Bonsai's text file
            if exist(sessionInfoPath, 'file')
                tmpFid = fopen(sessionInfoPath, 'r');
                line = fgetl(tmpFid);
                fclose(tmpFid);
                if ischar(line) && ~isempty(strtrim(line))
                    csvPath = strtrim(line);
                    disp(['Read session path from Bonsai: ' csvPath])
                else
                    warning('next_session.txt was empty — using timestamp fallback.');
                    csvPath = fullfile(csvOutputDir, ['BpodLog_' datestr(now, 'yyyymmdd_HHMMSS') '.csv']);
                end
            else
                warning('next_session.txt not found at %s — using timestamp fallback.', sessionInfoPath);
                csvPath = fullfile(csvOutputDir, ['BpodLog_' datestr(now, 'yyyymmdd_HHMMSS') '.csv']);
            end

            % Create directory if it doesn't exist
            csvDir = fileparts(csvPath);
            if ~exist(csvDir, 'dir'), mkdir(csvDir); end
            fid = fopen(csvPath, 'w');
            fprintf(fid, 'Trial,Type,Name,Timestamp\n');
            trialNum = 0;
            sessionWallAnchor = [];
            sessionBpodAnchor = [];
            disp(['New session — logging to ' csvPath])

            % This trial was just the SessionStart handshake, skip logging it
            continue
        end

        % =============================================
        % SESSION END — close CSV, reset, wait
        % =============================================
        if hitSessionEnd
            if fid > 0
                fclose(fid);
                fprintf('Session ended. Saved %d trials to %s\n', trialNum, csvPath);
            end
            fid = -1;
            csvPath = '';
            trialNum = 0;
            sessionWallAnchor = [];
            sessionBpodAnchor = [];
            disp('Waiting for next session...')
            continue
        end

        % =============================================
        % NORMAL TRIAL — log events to CSV
        % =============================================
        if fid < 0
            warning('Trial %d occurred but no CSV is open (no SessionStart yet). Skipping log.', trialNum);
            continue
        end

        entries = {};
        stateTS = rawEvents.StateTimestamps;
        for s = 1:numel(stateIndices)
            idx = stateIndices(s);
            if idx > 0 && idx <= numel(stateNames)
                sName = stateNames{idx};
                entries{end+1} = {stateTS(s), trialNum, 'State', sName};
                if softcodeMap.isKey(sName)
                    entries{end+1} = {stateTS(s), trialNum, 'Output', ['APP_SoftCode_' num2str(softcodeMap(sName))]};
                end
            end
        end
        eventIndices = rawEvents.Events;
        eventTS = rawEvents.EventTimestamps;
        for e = 1:numel(eventIndices)
            idx = eventIndices(e);
            if ~isempty(eventNameList) && idx > 0 && idx <= numel(eventNameList)
                eName = eventNameList{idx};
            else
                eName = ['Event_' num2str(idx)];
            end
            entries{end+1} = {eventTS(e), trialNum, 'Event', eName};
        end

        sortKeys = cellfun(@(x) x{1}, entries);
        [~, order] = sort(sortKeys);
        entries = entries(order);
        for i = 1:numel(entries)
            e = entries{i};
            bpodAbsTime = trialT0 + e{1};
            wallDT = sessionWallAnchor + seconds(bpodAbsTime - sessionBpodAnchor);
            wallStr = char(wallDT, 'yyyy-MM-dd''T''HH:mm:ss.SSSSSSxxx');
            fprintf(fid, '%d,%s,%s,%s\n', e{2}, e{3}, e{4}, wallStr);
        end
        disp(['Trial ' num2str(trialNum) ' logged.'])
    end
catch ME
    disp(['Error: ' ME.message])
end

% Clean up — close CSV if still open
if fid > 0
    fclose(fid);
    fprintf('Saved %d trials to %s\n', trialNum, csvPath);
end